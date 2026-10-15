#!/usr/bin/env python3
"""CLI integration tests for lexical and parsed RTL style checks.

These tests exercise only the rules that check_rtl.py claims to cover. They do
not establish Verilog correctness, synthesis support, timing, or CDC safety.
Run with: python test_check_rtl.py
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import check_rtl


CHECKER = Path(__file__).resolve().with_name("check_rtl.py")


def rtl_source(name="sample_unit", body=""):
    return (
        "`timescale 1ns/1ps\n"
        "`default_nettype none\n"
        f"module {name} (\n"
        "    input wire clk\n"
        ");\n"
        f"{body}"
        "endmodule\n"
        "`default_nettype wire\n"
    )


class CheckRtlCliTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="check_rtl_test_")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)

    def write_file(self, text=None, name="sample_unit.v", raw=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw is None:
            raw = (rtl_source() if text is None else text).encode("utf-8")
        path.write_bytes(raw)
        return path

    def run_checker(self, *paths, output_format="json"):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(CHECKER), *(str(path) for path in paths),
             "--format", output_format],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=15,
            check=False,
        )
        if output_format != "json":
            return result
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(
                f"Invalid JSON: {error}; returncode={result.returncode}; "
                f"stdout={result.stdout!r}; stderr={result.stderr!r}"
            )
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["exit_code"], result.returncode)
        return result, report

    @staticmethod
    def diagnostics(report, rule_id=None):
        entries = [item for file in report["files"]
                   for item in file["diagnostics"]]
        return entries if rule_id is None else [
            item for item in entries if item["rule_id"] == rule_id
        ]

    def assert_pass(self, path):
        result, report = self.run_checker(path)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report["status"], "pass")
        self.assertFalse(self.diagnostics(report), report)
        return report

    def assert_violation(self, path, rule_id, line=None, incomplete=False):
        result, report = self.run_checker(path)
        self.assertEqual(result.returncode, 2 if incomplete else 1, report)
        self.assertEqual(report["status"], "incomplete" if incomplete else "fail")
        matches = self.diagnostics(report, rule_id)
        self.assertTrue(matches, report)
        for item in matches:
            self.assertEqual(item["kind"], "violation")
            self.assertTrue(Path(item["path"]).is_absolute())
            self.assertEqual(Path(item["path"]).resolve(), path.resolve())
            self.assertGreaterEqual(item["line"], 1)
        if line is not None:
            self.assertIn(line, [item["line"] for item in matches], report)
        return report

    def assert_preprocessing_incomplete(self, path):
        result, report = self.run_checker(path)
        self.assertEqual(result.returncode, 2, report)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual([d["rule_id"] for d in self.diagnostics(report)], ["PARSE-001"])
        self.assertIn("PORT-001", report["files"][0]["unchecked_rules"])
        self.assertIn("FILE-001", report["files"][0]["checked_rules"])
        self.assertIn("SYN-001", report["files"][0]["checked_rules"])

    def test_minimal_module_passes(self):
        self.assert_pass(self.write_file())

    def test_structural_checker_exception_is_not_a_pass_or_crash(self):
        path = self.write_file()
        with patch.object(check_rtl, "check_source", side_effect=RuntimeError("parser visitor error")):
            report = check_rtl.build_report([str(path)])
        self.assertEqual(report["status"], "incomplete")
        diagnostic = self.diagnostics(report, "CHECK-003")[0]
        self.assertNotIn("reviewable", diagnostic)

    def test_preprocessing_and_syntax_failure_have_distinct_limits(self):
        macro = self.write_file("`define VALUE 1\n" + rtl_source())
        report = check_rtl.build_report([str(macro)])
        self.assertTrue(self.diagnostics(report, "PARSE-001")[0]["reviewable"])
        invalid = self.write_file(rtl_source(body="    always @(*) begin broken\n"))
        report = check_rtl.build_report([str(invalid)])
        self.assertTrue(self.diagnostics(report, "PARSE-001"))
        self.assertTrue(all(not d.get("reviewable") for d in self.diagnostics(report, "PARSE-001")))

    def test_chinese_comments_crlf_and_lexical_decoys_pass(self):
        body = (
            "    // 中文注释：module ghost; endmodule; defparam u.P = 1;\n"
            "    // 普通文字提到 full_case 和 parallel_case，不是综合提示。\n"
            "    /* `timescale 10ns/1ns\n"
            "       `default_nettype wire; module other; endmodule */\n"
            '    localparam [1023:0] NOTE = {"module fake; endmodule; ",\n'
            '        "`timescale 10ns/1ns; `default_nettype wire; defparam; ",\n'
            '        "synthesis full_case"};\n'
        )
        self.assert_pass(self.write_file(rtl_source(body=body).replace("\n", "\r\n")))

    def test_init_output_reg_and_loop_index_are_not_semantic_violations(self):
        source = (
            "`timescale 1ns/1ps\n"
            "`default_nettype none\n"
            "module sample_unit (\n"
            "    input wire clk,\n"
            "    output reg [7:0] data_o = 8'd0\n"
            ");\n"
            "    reg [7:0] count_reg = 8'd0;\n"
            "    integer idx_bit;\n"
            "    always @(posedge clk) begin\n"
            "        count_reg <= count_reg + 8'd1;\n"
            "        for (idx_bit = 0; idx_bit < 8; idx_bit = idx_bit + 1) begin\n"
            "            data_o[idx_bit] <= count_reg[idx_bit];\n"
            "        end\n"
            "    end\n"
            "endmodule\n"
            "`default_nettype wire\n"
        )
        self.assert_pass(self.write_file(source))

    def test_utf8_bom_is_accepted_for_parsing(self):
        self.assert_pass(self.write_file(raw=b"\xef\xbb\xbf" + rtl_source().encode("utf-8")))

    def test_invalid_utf8_is_incomplete(self):
        path = self.write_file(raw=b"\xff\xfeinvalid\n")
        result, report = self.run_checker(path)
        self.assertEqual(result.returncode, 2, report)
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(self.diagnostics(report, "INPUT-001"), report)

    def test_tab_is_reported_at_physical_line(self):
        self.assert_violation(
            self.write_file(rtl_source(body="\t// 一个 Tab\n")), "FMT-002", line=6,
        )

    def test_trailing_space_is_reported(self):
        self.assert_violation(
            self.write_file(rtl_source(body="    // trailing spaces  \n")),
            "FMT-003", line=6,
        )

    def test_missing_final_newline_is_reported(self):
        self.assert_violation(self.write_file(rtl_source().rstrip("\n")), "FMT-004")

    def test_line_length_limit(self):
        self.assert_pass(self.write_file(rtl_source(body="//" + "x" * 98 + "\n")))
        self.assert_violation(self.write_file(rtl_source(body="//" + "x" * 99 + "\n")),
                              "FMT-005", line=6)

    def test_module_name_must_match_filename(self):
        self.assert_violation(self.write_file(rtl_source("other_unit")), "FILE-001")

    def test_file_and_module_must_use_snake_case(self):
        self.assert_violation(
            self.write_file(rtl_source("SampleUnit"), name="SampleUnit.v"), "FILE-001",
        )

    def test_multiple_real_modules_are_reported(self):
        source = rtl_source().replace(
            "`default_nettype wire\n", "module another_unit;\nendmodule\n`default_nettype wire\n",
        )
        self.assert_violation(self.write_file(source), "FILE-001")

    def test_comment_only_module_does_not_count(self):
        self.assert_violation(
            self.write_file("// module sample_unit; endmodule\n"), "FILE-001",
            incomplete=True,
        )

    def test_vh_function_fragment_needs_no_module_or_directives(self):
        source = (
            "// 模块内包含的纯函数片段。\n"
            "function [7:0] invert_byte;\n"
            "    input [7:0] value;\n"
            "    begin\n"
            "        invert_byte = ~value;\n"
            "    end\n"
            "endfunction\n"
        )
        report = self.assert_pass(self.write_file(source, name="byte_functions.vh"))
        checked = report["files"][0]["checked_rules"]
        self.assertNotIn("FILE-001", checked)

    def test_vh_formatting_is_still_checked(self):
        self.assert_violation(self.write_file("\t// header\n", name="defs.vh"), "FMT-002")

    def test_timescale_is_optional_and_not_fixed_by_style(self):
        for replacement in ("", "`timescale 10ns/1ns\n", "// `timescale 1ns/1ps\n"):
            with self.subTest(replacement=replacement):
                source = rtl_source().replace("`timescale 1ns/1ps\n", replacement)
                self.assert_pass(self.write_file(source))

    def test_nettype_preamble_is_optional(self):
        for source in (rtl_source().replace("`default_nettype none\n", ""),
                       rtl_source().replace("`default_nettype wire\n", ""),
                       "module sample_unit;\nendmodule\n"):
            with self.subTest(source=source):
                self.assert_pass(self.write_file(source))

    def test_real_defparam_is_reported(self):
        self.assert_violation(
            self.write_file(rtl_source(body="    defparam u_example.WIDTH = 8;\n")),
            "SYN-001", line=6,
        )

    def test_real_synthesis_hints_require_semantic_review(self):
        for hint in (
            "    // synthesis full_case\n",
            "    /* synopsys parallel_case */\n",
            "    (* full_case *) wire option_wire;\n",
            "    (* parallel_case = 1 *) wire option_wire;\n",
        ):
            with self.subTest(hint=hint):
                result, report = self.run_checker(self.write_file(rtl_source(body=hint)))
                self.assertEqual(result.returncode, 2, report)
                matches = self.diagnostics(report, "SYN-002")
                self.assertTrue(matches, report)
                self.assertTrue(all(item["kind"] == "incomplete" for item in matches), report)
                self.assertIn(6, [item["line"] for item in matches], report)
                self.assertIn("SYN-002", report["files"][0]["unchecked_rules"])

    def test_tokens_with_keyword_substrings_do_not_match(self):
        body = (
            "    wire defparam_wire;\n"
            "    wire full_case_wire;\n"
            "    wire parallel_case_wire;\n"
            "    wire module_valid_wire;\n"
        )
        self.assert_pass(self.write_file(rtl_source(body=body)))

    def test_diagnostic_line_survives_multiline_comment_and_crlf(self):
        body = (
            "    /* module fake;\n"
            "       defparam ignored;\n"
            "       endmodule */\n"
            "    defparam u_example.WIDTH = 8;\n"
        )
        source = rtl_source(body=body).replace("\n", "\r\n")
        self.assert_violation(self.write_file(source), "SYN-001", line=9)

    def test_conditional_compilation_cannot_report_pass(self):
        source = "`ifdef SELECT_IMPLEMENTATION\n" + rtl_source() + "`endif\n"
        result, report = self.run_checker(self.write_file(source))
        self.assertEqual(result.returncode, 2, report)
        self.assertEqual(report["status"], "incomplete")
        self.assertTrue(self.diagnostics(report, "CHECK-002"), report)

    def test_preprocessing_does_not_hide_format_findings(self):
        source = "`ifdef SELECT_IMPLEMENTATION\n" + rtl_source(body="\t// tab\n") + "`endif\n"
        result, report = self.run_checker(self.write_file(source))
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(self.diagnostics(report, "CHECK-002"), report)
        self.assertTrue(self.diagnostics(report, "FMT-002"), report)

    def test_structure_generating_macro_is_incomplete(self):
        for source in (
            "`define MODULE_BODY module sample_unit; endmodule\n`MODULE_BODY\n",
            rtl_source().replace("module sample_unit", "module `MODULE_NAME"),
        ):
            with self.subTest(source=source):
                result, report = self.run_checker(self.write_file(source))
                self.assertEqual(result.returncode, 2, report)
                self.assertTrue(self.diagnostics(report, "CHECK-002"), report)

    def test_include_and_body_macros_allow_direct_source_checks(self):
        source = (
            '`include "not_opened_by_source_checker.vh"\n'
            + rtl_source(body="    wire result_wire;\n    assign result_wire = `DATA_EXPR;\n")
        )
        self.assert_preprocessing_incomplete(self.write_file(source))

    def test_vh_include_guard_allows_format_and_direct_syntax_checks(self):
        source = (
            "`ifndef EXAMPLE_DEFS_VH\n"
            "`define EXAMPLE_DEFS_VH\n"
            "`define EXAMPLE_WIDTH 8\n"
            "`endif\n"
        )
        self.assert_pass(self.write_file(source, name="example_defs.vh"))

    def test_preprocessor_macro_names_are_not_verilog_keywords(self):
        source = (
            "`ifndef defparam\n"
            "`define defparam\n"
            "`endif\n"
            "`ifdef module\n"
            "`elsif endmodule\n"
            "`endif\n"
            "`undef defparam\n"
        )
        self.assert_pass(self.write_file(source, name="macro_names.vh"))

    def test_macro_include_filename_is_not_a_structure_macro(self):
        source = "`include `HEADER_FILE\n" + rtl_source()
        self.assert_preprocessing_incomplete(self.write_file(source))

    def test_multiline_comment_in_macro_definition_hides_keyword_decoys(self):
        source = (
            "`define UNUSED_TEXT /* note\n"
            " module fake; defparam x.y = 1;\n"
            " */ 1\n"
            + rtl_source()
        )
        self.assert_preprocessing_incomplete(self.write_file(source))

    def test_unclosed_comment_in_macro_definition_is_incomplete(self):
        source = "`define UNUSED_TEXT /* unclosed\n" + rtl_source()
        result, report = self.run_checker(self.write_file(source))
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(self.diagnostics(report, "CHECK-001"), report)

    def test_unused_macro_body_is_not_scanned_as_running_code(self):
        source = "`define UNUSED_TEXT module ignored; defparam u.P = 1; endmodule\n" + rtl_source()
        self.assert_preprocessing_incomplete(self.write_file(source))

    def test_unterminated_lexical_construct_is_incomplete(self):
        for source in (rtl_source() + "/* unfinished\n", rtl_source(body='    "unfinished\n')):
            with self.subTest(source=source):
                result, report = self.run_checker(self.write_file(source))
                self.assertEqual(result.returncode, 2, report)
                self.assertTrue(self.diagnostics(report, "CHECK-001"), report)

    def test_missing_file_directory_and_unsupported_suffix_are_input_errors(self):
        unsupported = self.write_file(rtl_source(), name="sample_unit.sv")
        for path in (self.root / "missing.v", self.root, unsupported):
            with self.subTest(path=path):
                result, report = self.run_checker(path)
                self.assertEqual(result.returncode, 2, report)
                self.assertTrue(self.diagnostics(report, "INPUT-001"), report)

    def test_multiple_inputs_preserve_file_results(self):
        good = self.write_file(rtl_source("good_unit"), name="good_unit.v")
        bad = self.write_file(rtl_source("bad_unit", "\t// tab\n"), name="bad_unit.v")
        result, report = self.run_checker(good, bad)
        self.assertEqual(result.returncode, 1, report)
        self.assertEqual(len(report["files"]), 2)
        by_path = {Path(file["path"]).resolve(): file for file in report["files"]}
        self.assertEqual(by_path[good.resolve()]["status"], "pass")
        self.assertEqual(by_path[bad.resolve()]["status"], "fail")
        self.assertTrue(self.diagnostics(report, "FMT-002"), report)

    def test_input_error_has_priority_over_other_file_violation(self):
        bad = self.write_file(rtl_source(body="\t// tab\n"))
        result, report = self.run_checker(bad, self.root / "missing.v")
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(self.diagnostics(report, "FMT-002"), report)
        self.assertTrue(self.diagnostics(report, "INPUT-001"), report)

    def test_text_output_identifies_file_and_rule(self):
        path = self.write_file(rtl_source(body="\t// tab\n"))
        result = self.run_checker(path, output_format="text")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FMT-002", result.stdout)
        self.assertIn(path.name, result.stdout)

    def test_manual_baseline_preserves_only_existing_port_names(self):
        before = rtl_source().replace("input wire clk", "input wire sys_clk")
        baseline = self.write_file(before, name="before.txt")
        after = before.replace("endmodule", "    wire enabled_wire;\nendmodule")
        current = self.write_file(after)
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--format", "json", "--baseline", str(baseline),
             str(current)], capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("pass", json.loads(result.stdout)["status"])
        result, report = self.run_checker(current)
        self.assertEqual(1, result.returncode)
        self.assertTrue(self.diagnostics(report, "PORT-001"))


if __name__ == "__main__":
    unittest.main()

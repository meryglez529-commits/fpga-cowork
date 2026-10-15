#!/usr/bin/env python3
"""Behavior tests for the two-event hook using real temporary RTL files."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import rtl_check_hook as hook


def source(name="unit", extra=""):
    return ("`timescale 1ns/1ps\n`default_nettype none\n"
            f"module {name} (\n    input wire clk\n);\n{extra}"
            "endmodule\n`default_nettype wire\n")


class HookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rtl_hook_test_")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.work / "project"
        (self.root / ".git").mkdir(parents=True)
        self.rtl = self.root / "rtl"
        self.rtl.mkdir()
        self.cache = self.work / "state"
        self.references = hook.REFERENCES
        self.file = self.write("unit.v", source())

    def write(self, name, text):
        path = self.rtl / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def call(self, event, turn="t1", **extra):
        payload = {"session_id": "session", "turn_id": turn, "cwd": str(self.root),
                   "hook_event_name": event}
        payload.update(extra)
        return hook.handle(payload, ["rtl"], self.cache, self.references)

    def reports(self):
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.cache.rglob("report-*.json"))]

    def request(self):
        path = next(self.cache.rglob("review-request.json"))
        return json.loads(path.read_text(encoding="utf-8"))

    def review(self, transform=None):
        request = self.request()
        result = request["result_template"]
        for file_result in result["files"]:
            file_result["reviewed"] = True
        if transform:
            transform(result)
        Path(request["result_path"]).write_text(json.dumps(result), encoding="utf-8")
        return result

    def clean_change(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire enable_wire;\n"))
        return self.call("Stop")

    def test_clean_change_pass_and_coverage(self):
        self.assertEqual(self.call("UserPromptSubmit"), {})
        self.write("unit.v", source(extra="    wire enable_wire;\n"))
        result = self.call("Stop")
        self.assertEqual(result["decision"], "block")
        self.assertIn("机器检查 pass；AI 审查 missing", result["reason"])
        self.assertEqual(self.reports()[0]["machine_status"], "pass")
        self.assertEqual(self.reports()[0]["status"], "incomplete")
        self.assertEqual(self.reports()[0]["hook"]["changed_files"], ["rtl/unit.v"])
        self.review()
        self.assertIn("AI 已按请求范围补查", self.call("Stop")["systemMessage"])
        self.assertIn("pass", {report["status"] for report in self.reports()})

    def test_dirty_baseline_read_only_stays_quiet(self):
        self.write("unit.v", "bad RTL\t\n")
        self.call("UserPromptSubmit")
        self.assertEqual(self.call("Stop"), {})
        self.assertEqual(self.reports(), [])

    def test_existing_interface_survives_comment_edit_but_new_names_are_checked(self):
        before = """module unit (
    input wire sys_clk,
    input wire sys_rst_n,
    input wire enable,
    output reg result
);
    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            result <= 1'b0;
        end else begin
            result <= enable;
        end
    end
endmodule
"""
        self.write("unit.v", before)
        self.call("UserPromptSubmit")
        after = before.replace("    always @", "    // Retain the existing interface.\n    always @")
        self.write("unit.v", after)
        self.call("Stop")
        self.assertEqual("pass", self.reports()[-1]["machine_status"])
        self.review()
        self.assertIn("机器检查通过", self.call("Stop")["systemMessage"])

        self.call("UserPromptSubmit", turn="t2")
        self.write("unit.v", after.replace("    input wire enable,",
                                         "    input wire new_port,\n    input wire enable,"))
        self.call("Stop", turn="t2")
        failed = [report for report in self.reports() if report["machine_status"] == "fail"]
        self.assertEqual(1, len(failed))
        self.assertTrue(any(d["rule_id"] == "PORT-001" and "new_port" in d["message"]
                            for f in failed[0]["files"] for d in f["diagnostics"]))

    def test_fail_then_repair(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire enable_wire;\n"))
        first = self.call("Stop")
        self.assertEqual(first["decision"], "block")
        self.assertIn("rtl/unit.v:6 FMT-002", first["reason"])
        self.write("unit.v", source(extra="    wire enable_wire;\n"))
        self.call("Stop", stop_hook_active=True)
        self.review()
        result = self.call("Stop", stop_hook_active=True)
        self.assertIn("机器检查通过", result["systemMessage"])

    def test_incomplete_gets_one_retry_then_warning(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", "`ifdef TEST\n" + source() + "`endif\n")
        self.assertIn("incomplete", self.call("Stop")["reason"])
        result = self.call("Stop", stop_hook_active=True)
        self.assertNotIn("decision", result)
        self.assertIn("仍未通过", result["systemMessage"])
        self.assertEqual({r["status"] for r in self.reports()}, {"incomplete"})

    def test_changed_turn_keeps_failed_original_hash(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.call("Stop")
        self.call("UserPromptSubmit", turn="t2")
        result = self.call("Stop", turn="t2")
        self.assertEqual(result["decision"], "block")
        self.assertIn("机器检查 fail", result["reason"])
        self.call("UserPromptSubmit", turn="t3")
        self.assertEqual(self.call("Stop", turn="t3")["decision"], "block")

    def test_retry_flag_limits_repeated_stop_without_runtime_flag(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.assertEqual(self.call("Stop")["decision"], "block")
        for unused in range(2):
            self.assertIn("仍未通过", self.call("Stop")["systemMessage"])
        self.assertEqual(len(self.reports()), 3)

    def test_runtime_active_flag_prevents_another_continuation(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        result = self.call("Stop", stop_hook_active=True)
        self.assertNotIn("decision", result)
        self.assertIn("未通过", result["systemMessage"])

    def test_deleted_failed_file_is_ignored_on_retry(self):
        self.call("UserPromptSubmit")
        added = self.write("added.v", source("added", "\twire x_wire;\n"))
        self.call("Stop")
        self.call("UserPromptSubmit", turn="t2")
        added.unlink()
        self.assertEqual(self.call("Stop", turn="t2"), {})

    def test_sessions_keep_separate_baselines(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.call("UserPromptSubmit", session_id="another")
        self.assertEqual(self.call("Stop", session_id="another"), {})
        self.assertEqual(self.call("Stop")["decision"], "block")

    def test_file_changed_during_checker_cannot_report_pass(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        original = hook.build_report

        def racing(paths, **kwargs):
            report = original(paths, **kwargs)
            self.write("unit.v", source(extra="\twire x_wire;\n"))
            return report

        with patch.object(hook, "build_report", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_other_file_changed_during_checker_cannot_report_pass(self):
        self.write("other.v", source("other"))
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        original = hook.build_report

        def racing(paths, **kwargs):
            report = original(paths, **kwargs)
            self.write("other.v", source("other", "\twire x_wire;\n"))
            return report

        with patch.object(hook, "build_report", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_added_file_during_checker_cannot_report_pass(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        original = hook.build_report

        def racing(paths, **kwargs):
            report = original(paths, **kwargs)
            self.write("added.v", source("added", "\twire x_wire;\n"))
            return report

        with patch.object(hook, "build_report", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_same_turn_prompt_does_not_reset_baseline(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.call("UserPromptSubmit")
        self.assertEqual(self.call("Stop")["decision"], "block")

    def test_interrupted_turn_preserves_unchecked_changes(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.write("added.v", source("added", "\twire x_wire;\n"))
        self.call("UserPromptSubmit", turn="t2")
        result = self.call("Stop", turn="t2")
        self.assertEqual(result["decision"], "block")
        self.assertIn("rtl/unit.v", result["reason"])
        self.assertIn("rtl/added.v", result["reason"])

    def test_race_then_new_turn_still_checks_all_unchecked_changes(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        original = hook.build_report

        def racing(paths, **kwargs):
            report = original(paths, **kwargs)
            self.write("added.v", source("added", "\twire x_wire;\n"))
            return report

        with patch.object(hook, "build_report", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])
        self.call("UserPromptSubmit", turn="t2")
        result = self.call("Stop", turn="t2")
        self.assertEqual(result["decision"], "block")
        self.assertIn("rtl/added.v", result["reason"])
        self.assertEqual(self.reports()[0]["hook"]["changed_files"],
                         ["rtl/added.v", "rtl/unit.v"])

    def test_read_error_then_new_turn_preserves_unchecked_change(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        original = Path.read_bytes

        def broken(path):
            if path.resolve() == self.file.resolve():
                raise PermissionError("RTL read denied")
            return original(path)

        with patch.object(Path, "read_bytes", broken):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])
        self.call("UserPromptSubmit", turn="t2")
        self.assertEqual(self.call("Stop", turn="t2")["decision"], "block")

    def test_error_after_earlier_stop_does_not_leave_completion_mark(self):
        self.call("UserPromptSubmit")
        self.assertEqual(self.call("Stop"), {})
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        with patch.object(hook, "build_report", side_effect=OSError("checker read failed")):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])
        self.call("UserPromptSubmit", turn="t2")
        self.assertEqual(self.call("Stop", turn="t2")["decision"], "block")

    def test_new_failed_file_kept_across_turn(self):
        self.call("UserPromptSubmit")
        self.write("added.v", source("added", "\twire x_wire;\n"))
        self.call("Stop")
        self.call("UserPromptSubmit", turn="t2")
        self.assertIn("rtl/added.v", self.call("Stop", turn="t2")["reason"])

    def test_new_and_deleted_files(self):
        self.call("UserPromptSubmit")
        self.file.unlink()
        self.write("added.v", source("added"))
        self.call("Stop")
        self.assertEqual(self.reports()[0]["hook"]["changed_files"], ["rtl/added.v"])

    def test_subdirectory_cwd_and_hooks_root(self):
        (self.root / ".git").rmdir()
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "hooks.json").write_text("{}", encoding="utf-8")
        self.call("UserPromptSubmit", cwd=str(self.rtl))
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        self.assertEqual(self.call("Stop", cwd=str(self.rtl))["decision"], "block")

    def test_no_baseline_and_other_turn_are_not_checked(self):
        self.assertIn("未检查", self.call("Stop")["systemMessage"])
        self.call("UserPromptSubmit")
        self.assertIn("未检查", self.call("Stop", turn="other")["systemMessage"])

    def test_scope_escape_and_bad_payload(self):
        payload = {"session_id": "s", "turn_id": "t", "cwd": str(self.root),
                   "hook_event_name": "UserPromptSubmit"}
        for includes in (["../outside"], [str(self.rtl)], ["C:rtl"], ["rtl/../rtl"], []):
            self.assertIn("未检查", hook.handle(payload, includes, self.cache)["systemMessage"])
        self.assertIn("未检查", hook.handle([], ["rtl"], self.cache)["systemMessage"])

    def test_non_rtl_and_generated_directories_excluded(self):
        self.call("UserPromptSubmit")
        for name in ("notes.md", "vendor/a.v", "ip/b.v", "bd/c.v",
                     "test.runs/d.v", "test.gen/e.v", ".Xil/f.v", ".codex/g.v"):
            self.write(name, "bad\t\n")
        self.assertEqual(self.call("Stop"), {})
        self.write("header.vh", "`define WIDTH 8\n")
        self.call("Stop")
        self.assertEqual(self.reports()[0]["hook"]["changed_files"], ["rtl/header.vh"])

    def test_systemverilog_in_production_scope_cannot_escape_review(self):
        self.call("UserPromptSubmit")
        self.write("new_business.sv", "module new_business; endmodule\n")
        self.write("new_defs.svh", "`define NEW_WIDTH 8\n")
        result = self.call("Stop")
        self.assertEqual(result["decision"], "block")
        self.assertIn("机器检查 incomplete", result["reason"])
        self.assertIn("INPUT-001", result["reason"])
        request = self.request()
        self.assertEqual({item["relative_path"] for item in request["sources"]},
                         {"rtl/new_business.sv", "rtl/new_defs.svh"})
        self.assertIn("Verilog-2001", request["instructions"])
        self.review()
        self.assertIn("机器检查 incomplete", self.call("Stop")["systemMessage"])

    def test_testbench_outside_production_scope_is_not_scanned(self):
        self.call("UserPromptSubmit")
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "tb.sv").write_text("module tb; endmodule\n", encoding="utf-8")
        self.assertEqual(self.call("Stop"), {})

    def test_symlink_not_followed(self):
        outside = self.work / "outside"
        outside.mkdir()
        (outside / "bad.v").write_text("bad\t", encoding="utf-8")
        try:
            (self.rtl / "linked").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        self.call("UserPromptSubmit")
        self.assertEqual(self.call("Stop"), {})
        payload = {"session_id": "s", "turn_id": "t", "cwd": str(self.root),
                   "hook_event_name": "Stop"}
        self.assertIn("未检查", hook.handle(payload, ["rtl/linked"], self.cache)["systemMessage"])

    def test_read_failure_is_not_checked(self):
        self.call("UserPromptSubmit")
        original = Path.read_bytes

        def broken(path):
            if path.resolve() == self.file.resolve():
                raise PermissionError("RTL read denied")
            return original(path)

        with patch.object(Path, "read_bytes", broken):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_cli_emits_utf8_json_only(self):
        environment = os.environ.copy()
        environment["TEMP"] = str(self.work)
        environment["TMP"] = str(self.work)
        payload = {"session_id": "cli", "turn_id": "t", "cwd": str(self.root),
                   "hook_event_name": "Stop"}
        result = subprocess.run([sys.executable, str(Path(hook.__file__)), "--include", "rtl"],
                                input=json.dumps(payload), text=True, encoding="utf-8",
                                capture_output=True, env=environment, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn("未检查", json.loads(result.stdout)["systemMessage"])

    def test_request_defaults_to_unreviewed_without_chapter_proof(self):
        result = self.clean_change()
        request = self.request()
        self.assertIn("review-request.json", result["reason"])
        self.assertEqual(set(request["documents"]), set(hook.STANDARD_FILES))
        self.assertEqual(request["refresh_hook_input"]["hook_event_name"], "Stop")
        self.assertTrue(request["refresh_hook_input"]["stop_hook_active"])
        self.assertNotIn("transcript_path", request["refresh_hook_input"])
        self.assertEqual(request["schema_version"], 2)
        result_file = request["result_template"]["files"][0]
        self.assertEqual(set(result_file), {"path", "source_sha256", "reviewed", "findings"})
        self.assertFalse(result_file["reviewed"])
        self.assertEqual(result_file["findings"], [])
        self.assertEqual(request["machine_check"]["status"], "pass")
        self.assertTrue(request["machine_check"]["summary"]["implemented_rules"])
        self.assertTrue(request["machine_check"]["files"][0]["checked_rules"])
        for info in request["documents"].values():
            self.assertFalse(any(section["title"] in {"参考", "统一实现方式与专题入口"}
                                 for section in info["sections"]))

    def test_unfilled_template_never_passes(self):
        self.clean_change()
        request = self.request()
        Path(request["result_path"]).write_text(json.dumps(request["result_template"]),
                                               encoding="utf-8")
        result = self.call("Stop")
        self.assertIn("AI 审查 incomplete", result["systemMessage"])

    def test_source_change_expires_review(self):
        self.clean_change()
        self.review()
        self.write("unit.v", source(extra="    wire other_wire;\n"))
        result = self.call("Stop")
        self.assertIn("AI 审查 stale", result["systemMessage"])
        self.review()
        self.assertIn("机器检查通过", self.call("Stop")["systemMessage"])

    def test_standard_including_inline_example_change_expires_review(self):
        self.references = self.work / "references"
        shutil.copytree(hook.REFERENCES, self.references)
        self.clean_change()
        for change in (lambda text: text + "\n测试规范变更。\n",
                       lambda text: text.replace("parameter DATA_WIDTH = 8", "parameter DATA_WIDTH = 16")):
            self.review()
            path = self.references / "rtl-coding-standard.md"
            path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")
            self.assertIn("AI 审查 stale", self.call("Stop")["systemMessage"])

    def test_workflow_references_do_not_expire_style_review(self):
        self.references = self.work / "references"
        shutil.copytree(hook.REFERENCES, self.references)
        self.clean_change()
        self.review()
        for name in ("project-context.md", "simulation-environment.md", "build-environment.md",
                     "hardware-debug-environment.md", "read-only-diagnostics.md"):
            (self.references / name).unlink()
        self.assertIn("机器检查通过", self.call("Stop")["systemMessage"])

    def test_inline_example_is_not_a_rule_source(self):
        self.clean_change()
        request = self.request()
        self.assertEqual(set(request["documents"]), {"rtl-coding-standard.md"})
        sections = {s["section"] for s in request["documents"]["rtl-coding-standard.md"]["sections"]}
        self.assertEqual(sections, {str(i) for i in range(1, 9)})
        self.review(lambda r: self.finding(r, section="9"))
        self.assertIn("AI 审查 incomplete", self.call("Stop")["systemMessage"])

    def test_missing_review_file_or_confirmation_is_incomplete(self):
        self.clean_change()
        for transform in (lambda r: r["files"].clear(),
                          lambda r: r["files"][0].pop("reviewed"),
                          lambda r: r["files"][0].update(reviewed=1),
                          lambda r: r["files"][0].pop("findings")):
            self.review(transform)
            self.assertIn("AI 审查 incomplete", self.call("Stop")["systemMessage"])

    def test_duplicate_or_unknown_file_is_incomplete(self):
        self.clean_change()
        self.write("other.v", source("other"))
        self.call("Stop")
        for transform in (lambda r: r["files"].__setitem__(1, r["files"][0]),
                          lambda r: r["files"][0].update(path="rtl/unknown.v")):
            self.review(transform)
            self.assertIn("AI 审查 incomplete", self.call("Stop")["systemMessage"])

    def test_old_schema_is_rejected(self):
        self.clean_change()
        self.review(lambda r: r.update(schema_version=1))
        self.assertIn("schema_version 必须为 2", self.call("Stop")["systemMessage"])

    def finding(self, result, **fields):
        item = {"document": hook.STANDARD_FILES[0], "section": "1", "status": "fail",
                "lines": [1], "reason": "测试夹具中的已知规范问题。"}
        item.update(fields)
        result["files"][0]["findings"] = [item]

    def test_findings_need_valid_rule_reason_and_source_lines(self):
        self.clean_change()
        for fields in ({"reason": " "}, {"lines": []}, {"lines": [0]},
                       {"lines": [999]}, {"lines": [True]}, {"lines": ["1"]},
                       {"document": "unknown.md"}, {"section": "999"},
                       {"status": "pass"}, {"status": "not_applicable"}):
            self.review(lambda r: self.finding(r, **fields))
            self.assertIn("AI 审查 incomplete", self.call("Stop")["systemMessage"])

    def test_no_findings_needs_no_topic_or_pass_proof(self):
        self.clean_change()
        result = self.review()
        self.assertEqual(set(result["files"][0]), {"path", "source_sha256", "reviewed", "findings"})
        self.assertIn("机器检查通过", self.call("Stop")["systemMessage"])

    def test_standard_finding_or_unresolved_cannot_pass(self):
        self.clean_change()
        for status in ("fail", "unresolved"):
            self.review(lambda r: self.finding(r, status=status))
            message = self.call("Stop")["systemMessage"]
            self.assertIn("AI 审查 fail", message)
            self.assertIn("rtl/unit.v:1 rtl-coding-standard.md §1", message)
            self.assertIn("仍未通过", message)

    def test_ai_pass_cannot_override_machine_fail_or_incomplete(self):
        self.call("UserPromptSubmit")
        for content, status in ((source(extra="\twire x_wire;\n"), "fail"),
                                (source(extra="    wire [7:0 broken_wire;\n"), "incomplete")):
            self.write("unit.v", content)
            self.call("Stop")
            self.review()
            message = self.call("Stop")["systemMessage"]
            self.assertIn("机器检查 " + status, message)
            self.assertIn("AI 审查 pass", message)
            self.assertIn("仍未通过", message)

    def test_missing_review_remains_pending_after_warning_and_new_prompt(self):
        self.clean_change()
        self.assertIn("仍未通过", self.call("Stop", stop_hook_active=True)["systemMessage"])
        self.call("UserPromptSubmit", turn="t2")
        self.assertEqual(self.call("Stop", turn="t2")["decision"], "block")
        self.review()
        self.assertIn("机器检查通过", self.call("Stop", turn="t2")["systemMessage"])
        self.call("UserPromptSubmit", turn="t3")
        self.assertEqual(self.call("Stop", turn="t3"), {})

    def test_automatic_continuation_with_new_turn_does_not_block_again(self):
        self.clean_change()
        self.call("UserPromptSubmit", turn="t2")
        result = self.call("Stop", turn="t2", stop_hook_active=True)
        self.assertNotIn("decision", result)
        self.assertIn("仍未通过", result["systemMessage"])

    def test_additional_file_expires_old_review(self):
        self.clean_change()
        self.review()
        self.write("added.v", source("added"))
        self.assertIn("AI 审查 stale", self.call("Stop")["systemMessage"])
        self.assertEqual(len(self.request()["result_template"]["files"]), 2)

    def test_review_corruption_is_explicitly_incomplete(self):
        self.clean_change()
        path = Path(self.request()["result_path"])
        for content in ("not json", "[]", '{"schema_version":1}'):
            path.write_text(content, encoding="utf-8")
            self.assertIn("AI 审查 incomplete", self.call("Stop")["systemMessage"])

    def test_standard_changes_during_check_cannot_pass(self):
        self.references = self.work / "references"
        shutil.copytree(hook.REFERENCES, self.references)
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        original = hook.build_report

        def racing(paths, **kwargs):
            report = original(paths, **kwargs)
            path = self.references / "rtl-coding-standard.md"
            path.write_text(path.read_text(encoding="utf-8") + "\n变更\n", encoding="utf-8")
            return report

        with patch.object(hook, "build_report", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_legacy_hook_state_can_require_review_without_being_reset(self):
        self.call("UserPromptSubmit")
        state_path = next(self.cache.rglob("state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 1)
        state.pop("baseline_text")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        result = self.call("Stop")
        self.assertEqual(result["decision"], "block")
        self.assertIn("AI 审查 missing", result["reason"])
        scope = self.request()["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "full")
        self.assertEqual(scope["reason"], "baseline_text_unavailable")

    def test_small_change_has_actual_diff_and_affected_context_scope(self):
        self.clean_change()
        request = self.request()
        scope = request["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "changed_with_context")
        self.assertIn("+    wire enable_wire;", scope["diff"])
        self.assertEqual(scope["changes"], [
            {"old_start": 6, "old_count": 0, "new_start": 6, "new_count": 1}])
        self.assertIn("不能只读 diff", request["instructions"])
        self.assertIn("状态、握手、时钟、复位", request["instructions"])
        self.assertEqual(request["machine_check"]["files"][0]["path"], str(self.file.resolve()))

    def test_new_file_requests_full_scope(self):
        self.call("UserPromptSubmit")
        self.write("added.v", source("added"))
        self.call("Stop")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertEqual(scope, {"mode": "full", "baseline_sha256": None, "reason": "new_file"})

    def test_deleted_lines_are_present_in_diff(self):
        self.write("unit.v", source(extra="    wire removed_wire;\n"))
        self.call("UserPromptSubmit")
        self.write("unit.v", source())
        self.call("Stop")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "changed_with_context")
        self.assertEqual(scope["changes"], [
            {"old_start": 6, "old_count": 1, "new_start": 6, "new_count": 0}])
        self.assertIn("-    wire removed_wire;", scope["diff"])

    def test_machine_preprocessor_gap_requests_full_scope(self):
        content = "`ifdef TEST\n" + source() + "`endif\n"
        self.write("unit.v", content)
        self.call("UserPromptSubmit")
        self.write("unit.v", content + "// small edit\n")
        self.call("Stop")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "full")
        self.assertEqual(scope["reason"], "machine_coverage_gap")

    def test_large_rewrite_requests_full_scope(self):
        self.write("unit.v", source(extra="".join(f"    wire old_{i}_c;\n" for i in range(20))))
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="".join(f"    wire new_{i}_c;\n" for i in range(20))))
        self.call("Stop")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "full")
        self.assertEqual(scope["reason"], "large_change")

    def test_removing_preprocessor_construct_also_requests_full_scope(self):
        self.write("unit.v", source(extra="`define OLD_UNUSED 1\n"))
        self.call("UserPromptSubmit")
        self.write("unit.v", source())
        self.call("Stop")
        request = self.request()
        self.assertEqual(request["machine_check"]["status"], "pass")
        scope = request["sources"][0]["review_scope"]
        self.assertEqual(scope["mode"], "full")
        self.assertEqual(scope["reason"], "baseline_structure_unavailable")

    def test_pending_turn_preserves_original_text_and_diff(self):
        original = source(extra="    wire original_wire;\n")
        self.write("unit.v", original)
        original_bytes = self.file.read_bytes()
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire intermediate_wire;\n"))
        self.call("Stop")
        self.call("UserPromptSubmit", turn="t2")
        self.write("unit.v", source(extra="    wire final_wire;\n"))
        self.call("Stop", turn="t2")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertIn("-    wire original_wire;", scope["diff"])
        self.assertIn("+    wire final_wire;", scope["diff"])
        self.assertNotIn("intermediate_wire", scope["diff"])
        state = json.loads(next(self.cache.rglob("state.json")).read_text(encoding="utf-8"))
        self.assertEqual(state["baseline_text"]["rtl/unit.v"].encode("utf-8"), original_bytes)

    def test_interrupted_turn_preserves_text_baseline(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra="    wire interrupted_wire;\n"))
        self.call("UserPromptSubmit", turn="t2")
        self.call("Stop", turn="t2")
        self.assertIn("+    wire interrupted_wire;", self.request()["sources"][0]["review_scope"]["diff"])

    def test_successful_new_turn_refreshes_text_baseline(self):
        self.clean_change()
        self.review()
        self.call("Stop")
        self.call("UserPromptSubmit", turn="t2")
        self.write("unit.v", source(extra="    wire final_wire;\n"))
        self.call("Stop", turn="t2")
        scope = self.request()["sources"][0]["review_scope"]
        self.assertIn("-    wire enable_wire;", scope["diff"])
        self.assertIn("+    wire final_wire;", scope["diff"])

    def test_corrupt_or_missing_text_falls_back_and_expires_scope_receipt(self):
        self.clean_change()
        self.review()
        request_id = self.request()["review_id"]
        state_path = next(self.cache.rglob("state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["baseline_text"]["rtl/unit.v"] = "not the original source"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = self.call("Stop")
        self.assertIn("AI 审查 stale", result["systemMessage"])
        request = self.request()
        self.assertNotEqual(request_id, request["review_id"])
        self.assertEqual(request["sources"][0]["review_scope"]["mode"], "full")

    def test_baseline_storage_limits_fall_back_without_losing_hashes(self):
        for limits in ({"BASELINE_FILE_BYTES": 10}, {"BASELINE_TOTAL_BYTES": 10}):
            with patch.multiple(hook, **limits):
                self.call("UserPromptSubmit", session_id=str(limits))
                self.write("unit.v", source(extra="    wire large_wire;\n"))
                self.call("Stop", session_id=str(limits))
            self.write("unit.v", source())
        states = [json.loads(p.read_text(encoding="utf-8")) for p in self.cache.rglob("state.json")]
        self.assertTrue(all(state["baseline_text"] == {} and "rtl/unit.v" in state["baseline"]
                            for state in states))
        requests = [json.loads(p.read_text(encoding="utf-8"))
                    for p in self.cache.rglob("review-request.json")]
        self.assertTrue(all(r["sources"][0]["review_scope"]["mode"] == "full" for r in requests))

    def test_cli_refresh_after_fix_and_review_closes_loop(self):
        environment = os.environ.copy()
        environment["TEMP"] = str(self.work)
        environment["TMP"] = str(self.work)
        argv = [sys.executable, str(Path(hook.__file__)), "--include", "rtl"]
        payload = {"session_id": "cli-full", "turn_id": "t", "cwd": str(self.root),
                   "hook_event_name": "UserPromptSubmit"}

        def invoke(arguments, data):
            run = subprocess.run(arguments, input=json.dumps(data), text=True, encoding="utf-8",
                                 capture_output=True, env=environment, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stderr, "")
            return json.loads(run.stdout)

        self.assertEqual(invoke(argv, payload), {})
        self.write("unit.v", source(extra="\twire x_wire;\n"))
        payload["hook_event_name"] = "Stop"
        self.assertEqual(invoke(argv, payload)["decision"], "block")
        self.cache = self.work / "fpga-cowork-rtl-hooks"
        request = self.request()
        previous_id = request["review_id"]
        self.write("unit.v", source(extra="    wire x_wire;\n"))
        message = invoke(request["refresh_hook_argv"], request["refresh_hook_input"])
        self.assertIn("机器检查 pass；AI 审查 missing", message["systemMessage"])
        self.assertNotEqual(previous_id, self.request()["review_id"])
        self.review()
        message = invoke(argv, payload)
        self.assertIn("机器检查通过", message["systemMessage"])
        self.assertNotIn("decision", message)

    def test_only_explicit_reviewable_limits_can_complete_after_ai_review(self):
        original = hook.build_report

        def reviewable(paths, **kwargs):
            report = original(paths, **kwargs)
            for file_result in report["files"]:
                for diagnostic in file_result["diagnostics"]:
                    if diagnostic["kind"] == "incomplete":
                        diagnostic["reviewable"] = True
            return report

        self.call("UserPromptSubmit")
        self.write("unit.v", "`ifdef TEST\n" + source() + "`endif\n")
        with patch.object(hook, "build_report", reviewable):
            self.assertEqual(self.call("Stop")["decision"], "block")
            self.review()
            result = self.call("Stop")
        self.assertIn("reviewed_with_limits", result["systemMessage"])
        self.assertIn("机器检查仍为 incomplete", result["systemMessage"])
        reports = [report for report in self.reports() if report["status"] == "reviewed_with_limits"]
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["machine_status"], "incomplete")
        self.call("UserPromptSubmit", turn="t2")
        self.assertEqual(self.call("Stop", turn="t2"), {})

    def test_reviewable_flag_never_hides_a_definite_violation(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", "`ifdef TEST\n" + source(extra="\twire x_wire;\n") + "`endif\n")
        original = hook.build_report

        def reviewable(paths, **kwargs):
            report = original(paths, **kwargs)
            for file_result in report["files"]:
                for diagnostic in file_result["diagnostics"]:
                    diagnostic["reviewable"] = True
            return report

        with patch.object(hook, "build_report", reviewable):
            self.call("Stop")
            self.review()
            result = self.call("Stop")
        self.assertIn("仍未通过", result["systemMessage"])
        self.assertNotIn("reviewed_with_limits", result["systemMessage"])

    def test_unmarked_machine_gap_never_completes_with_ai_pass(self):
        self.call("UserPromptSubmit")
        self.write("unit.v", "`ifdef TEST\n" + source() + "`endif\n")
        original = hook.build_report

        def unmarked(paths, **kwargs):
            report = original(paths, **kwargs)
            for file_result in report["files"]:
                for diagnostic in file_result["diagnostics"]:
                    diagnostic.pop("reviewable", None)
            return report

        with patch.object(hook, "build_report", unmarked):
            self.call("Stop")
            self.review()
            result = self.call("Stop")
        self.assertIn("仍未通过", result["systemMessage"])

    def test_recursive_include_hashes_bind_review_and_ignore_comments(self):
        headers = self.root / "headers"
        headers.mkdir()
        (headers / "first.vh").write_text('`include "second.vh"\n', encoding="utf-8")
        second = headers / "second.vh"
        second.write_text('`define TEST_WIDTH 8\n// `include "missing.vh"\n', encoding="utf-8")
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra='`include "../headers/first.vh"\n'))
        self.call("Stop")
        request = self.request()
        self.assertEqual(set(request["review_dependencies"]),
                         {"headers/first.vh", "headers/second.vh"})
        self.assertEqual(request["dependency_issues"], [])
        self.review()
        second.write_text('`define TEST_WIDTH 16\n', encoding="utf-8")
        self.assertIn("AI 审查 stale", self.call("Stop")["systemMessage"])

    def test_missing_macro_or_outside_include_remains_incomplete(self):
        self.call("UserPromptSubmit")
        for include in ('`include "missing.vh"\n', '`include `HEADER_FILE\n',
                        '`include "../../outside.vh"\n'):
            self.write("unit.v", source(extra=include))
            self.call("Stop")
            self.assertTrue(self.request()["dependency_issues"])
            self.review()
            result = self.call("Stop")
            self.assertIn("仍未通过", result["systemMessage"])
            self.assertNotIn("reviewed_with_limits", result["systemMessage"])

    def test_include_dependency_change_during_check_cannot_complete(self):
        headers = self.root / "headers"
        headers.mkdir()
        path = headers / "defs.vh"
        path.write_text("`define TEST_WIDTH 8\n", encoding="utf-8")
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra='`include "../headers/defs.vh"\n'))
        original = hook._review_result

        def racing(request, result_path):
            result = original(request, result_path)
            path.write_text("`define TEST_WIDTH 16\n", encoding="utf-8")
            return result

        with patch.object(hook, "_review_result", racing):
            self.assertIn("未检查", self.call("Stop")["systemMessage"])

    def test_include_cycle_is_bounded_and_every_branch_is_collected(self):
        headers = self.root / "headers"
        headers.mkdir()
        (headers / "first.vh").write_text('`include "second.vh"\n', encoding="utf-8")
        (headers / "second.vh").write_text('`include "first.vh"\n', encoding="utf-8")
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra='`ifdef TEST\n`include "../headers/first.vh"\n'
                                    '`else\n`include "../headers/second.vh"\n`endif\n'))
        self.call("Stop")
        request = self.request()
        self.assertEqual(set(request["review_dependencies"]),
                         {"headers/first.vh", "headers/second.vh"})
        self.assertEqual(request["dependency_issues"], [])

    def test_known_header_violation_cannot_be_overridden_by_ai_review(self):
        headers = self.root / "headers"
        headers.mkdir()
        path = headers / "defs.vh"
        path.write_text("\tlocalparam [7:0] TEST_WIDTH = 8'd8;\n", encoding="utf-8")
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra='`include "../headers/defs.vh"\n'))
        result = self.call("Stop")
        self.assertIn("headers/defs.vh:1 FMT-002", result["reason"])
        self.review()
        result = self.call("Stop")
        self.assertIn("仍未通过", result["systemMessage"])
        self.assertNotIn("reviewed_with_limits", result["systemMessage"])

    def test_literal_include_symlink_is_not_read(self):
        headers = self.root / "headers"
        headers.mkdir()
        target = self.work / "external.vh"
        target.write_text("`define TEST_WIDTH 8\n", encoding="utf-8")
        try:
            (headers / "linked.vh").symlink_to(target)
        except OSError as error:
            self.skipTest(str(error))
        self.call("UserPromptSubmit")
        self.write("unit.v", source(extra='`include "../headers/linked.vh"\n'))
        self.call("Stop")
        request = self.request()
        self.assertEqual(request["review_dependencies"], {})
        self.assertTrue(request["dependency_issues"])


if __name__ == "__main__":
    unittest.main()

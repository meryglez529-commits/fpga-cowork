"""Real-parser regression tests, including intentional coding violations."""

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rtl_structure as checker
from check_rtl import build_report


def wrap(body, ports="input wire clk, input wire data_i, output reg data_o"):
    return "module test(" + ports + ");\n" + body + "\nendmodule\n"


FSM = """localparam [1:0] ST_IDLE = 2'd0;
localparam [1:0] ST_RUN = 2'd1;
reg [1:0] state_reg;
reg [1:0] next_state_wire;
always @(posedge clk) begin
    if (data_i) begin
        state_reg <= ST_IDLE;
    end else begin
        state_reg <= next_state_wire;
    end
end
always @(*) begin
    next_state_wire = state_reg;
    case (state_reg)
        ST_IDLE: begin
            next_state_wire = ST_RUN;
        end
        default: begin
            next_state_wire = ST_IDLE;
        end
    endcase
end
always @(posedge clk) begin
    data_o <= (next_state_wire == ST_RUN);
end
"""


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checker._load_parser()  # Missing dependency fails tests, never silently skips.

    def check(self, body, ports=None):
        text = wrap(body, ports) if ports is not None else wrap(body)
        return checker.check_source(path="test.v", text=text)

    def violations(self, report, rule):
        return [d for d in report["diagnostics"]
                if d["rule_id"] == rule and d["kind"] == "violation"]

    def test_clean_fsm(self):
        self.assertEqual([], self.check(FSM)["diagnostics"])

    def test_fixed_clock_reset_and_domain_port_names(self):
        ports = ("input wire clk, input wire rst_n, input wire rst_n_async, "
                 "input wire clk_core, input wire rst_n_core")
        self.assertEqual([], self.check("", ports)["diagnostics"])
        for name in ("clk_i", "rst_n_i", "data_reg_o", "data_wire_o"):
            with self.subTest(name=name):
                self.assertTrue(self.violations(self.check("", "output wire " + name), "PORT-001"))

    def test_legacy_internal_suffixes_are_rejected(self):
        self.assertEqual(2, len(self.violations(self.check("reg count_q;\nreg selected_c;"), "NAME-001")))

    def test_comb_reg_variable_uses_wire_suffix(self):
        r = self.check("reg selected_wire;\nalways @(*) begin\n    selected_wire = data_i;\nend")
        self.assertEqual([], r["diagnostics"])

    def test_prefixed_fsm_names(self):
        r = self.check(FSM.replace("state_reg", "rx_state_reg")
                       .replace("next_state_wire", "rx_next_state_wire"))
        self.assertEqual([], r["diagnostics"])

    def test_wire_declaration_separate_from_assignment(self):
        bad = self.check("wire selected_wire = data_i;")
        self.assertTrue(self.violations(bad, "DECL-002"))
        good = self.check("wire selected_wire;\nassign selected_wire = data_i;")
        self.assertEqual([], good["diagnostics"])

    def test_continuous_and_mixed_multiple_drivers(self):
        for body in ("wire selected_wire;\nassign selected_wire = 1'b0;\nassign selected_wire = 1'b1;",
                     "reg selected_wire;\nalways @(*) begin\nselected_wire = data_i;\nend\n"
                     "assign selected_wire = 1'b0;"):
            with self.subTest(body=body):
                self.assertTrue(self.violations(self.check(body), "DRIVER-001"))

    def test_async_reset_not_counted_as_second_working_clock(self):
        body = "reg flag_reg;\nalways @(posedge clk or negedge rst_n) begin\nflag_reg <= 1'b0;\nend"
        self.assertEqual([], self.check(body, "input wire clk, input wire rst_n")["diagnostics"])
        body = body.replace("negedge rst_n", "posedge clk_other")
        self.assertTrue(self.violations(self.check(body, "input wire clk, input wire clk_other"), "PROC-002"))

    def test_generate_and_function_names(self):
        self.assertTrue(self.violations(self.check(
            "generate if (1) begin: lane\nchild u_child();\nend endgenerate"), "NAME-001"))
        self.assertTrue(self.violations(self.check(
            "function Compute;\ninput value;\nbegin\nCompute = value;\nend\nendfunction"), "NAME-001"))

    def test_prefixed_reset_and_existing_port_names(self):
        text = wrap("""always @(posedge sys_clk or negedge sys_rst_n) begin
    if (!sys_rst_n) begin
        result <= 1'b0;
    end else begin
        result <= enable;
    end
end""", "input wire sys_clk, input wire sys_rst_n, input wire enable, output reg result")
        checked = checker.check_source("test.v", text, existing_text=text)
        self.assertEqual([], checked["diagnostics"])
        changed = text.replace("input wire enable", "input wire new_port, input wire enable")
        checked = checker.check_source("test.v", changed, existing_text=text)
        errors = self.violations(checked, "PORT-001")
        self.assertEqual(1, len(errors))
        self.assertIn("new_port", errors[0]["message"])
        self.assertTrue(self.violations(checker.check_source("test.v", text), "PORT-001"))
        checked = checker.check_source("test.v", wrap("", "input wire sys_clk"),
                                       existing_text="module test(sys_clk); input wire sys_clk; endmodule")
        errors = [d for d in checked["diagnostics"] if d["rule_id"] == "PORT-001"]
        self.assertEqual(1, len(errors))
        self.assertEqual("incomplete", errors[0]["kind"])
        self.assertTrue(errors[0]["reviewable"])

    def test_clock_name_fields_keep_multiple_clocks_and_unknown_roles_distinct(self):
        for other, kind in (("clk_other", "violation"), ("burst_i", "incomplete")):
            with self.subTest(other=other):
                body = ("reg flag_reg;\nalways @(posedge clk or negedge " + other + ") begin\n"
                        "    flag_reg <= 1'b0;\nend")
                checked = self.check(body, "input wire clk, input wire " + other)
                errors = [d for d in checked["diagnostics"] if d["rule_id"] == "PROC-002"]
                self.assertEqual(1, len(errors))
                self.assertEqual(kind, errors[0]["kind"])
                if kind == "incomplete":
                    self.assertTrue(errors[0]["reviewable"])

    def test_casex_outside_fsm_is_rejected(self):
        body = "always @(*) begin\ncasex (data_i)\ndefault: begin\ndata_o = 1'b0;\nend\nendcase\nend"
        self.assertTrue(self.violations(self.check(body), "CASE-001"))

    def test_implicit_sensitivity_requires_parentheses(self):
        self.assertTrue(self.violations(self.check(
            "always @* begin\ndata_o = data_i;\nend"), "PROC-002"))

    def test_skill_examples(self):
        path = Path(__file__).parent.parent / "references" / "rtl-coding-standard.md"
        source = path.read_text(encoding="utf-8")
        modules = [b for b in re.findall(r"~~~verilog\n(.*?)~~~", source, re.S) if "module " in b]
        self.assertTrue(modules, "Style examples must contain complete modules")
        with tempfile.TemporaryDirectory(prefix="rtl_style_examples_") as directory:
            for module in modules:
                name = re.search(r"\bmodule\s+(\w+)", module)[1]
                with self.subTest(module=name):
                    target = Path(directory) / (name + ".v")
                    target.write_text(module, encoding="utf-8")
                    report = build_report([target])
                    self.assertEqual("pass", report["status"], report)

    def test_port_direction_suffix(self):
        self.assertTrue(self.violations(self.check("", "input wire clk, output reg data_i"), "PORT-001"))

    def test_port_explicit_type(self):
        self.assertTrue(self.violations(self.check("", "input clk"), "PORT-001"))

    def test_inherited_port_direction(self):
        self.assertTrue(self.violations(self.check("", "input wire clk, data_i"), "PORT-001"))

    def test_non_ansi_ports(self):
        r = checker.check_source("test.v", "module test(clk); input wire clk; endmodule")
        self.assertTrue(self.violations(r, "PORT-001"))

    def test_no_stacked_port_suffix(self):
        self.assertTrue(self.violations(self.check("", "output wire data_reg_o"), "PORT-001"))

    def test_clocked_blocking_violation(self):
        r = self.check("reg data_reg;\nalways @(posedge clk) begin\n    data_reg = data_i;\nend")
        self.assertTrue(self.violations(r, "PROC-001"))

    def test_comb_nonblocking_violation(self):
        r = self.check("reg data_wire;\nalways @(*) begin\n    data_wire <= data_i;\nend")
        self.assertTrue(self.violations(r, "PROC-001"))

    def test_function_blocking_is_not_clocked_assignment(self):
        r = self.check("""function calculate;
    input value;
    begin
        calculate = value;
    end
endfunction
always @(posedge clk) begin
    data_o <= calculate(data_i);
end""")
        self.assertEqual([], r["diagnostics"])

    def test_loop_header_exempt_but_body_not(self):
        r = self.check("""reg [7:0] data_reg;
integer idx_bit;
always @(posedge clk) begin
    for (idx_bit = 0; idx_bit < 8; idx_bit = idx_bit + 1) begin
        data_reg[idx_bit] <= data_i;
    end
end""")
        self.assertEqual([], r["diagnostics"])
        r = self.check("""reg [7:0] data_reg;
integer idx_bit;
always @(posedge clk) begin
    for (idx_bit = 0; idx_bit < 8; idx_bit = idx_bit + 1) begin
        data_reg[idx_bit] = data_i;
    end
end""")
        self.assertEqual(1, len(self.violations(r, "PROC-001")))

    def test_role_names(self):
        r = self.check("""reg data_wire;
reg sum_reg;
always @(posedge clk) begin
    data_wire <= data_i;
end
always @(*) begin
    sum_reg = data_i;
end""")
        self.assertEqual(2, len(self.violations(r, "NAME-001")))

    def test_parameters_and_instance_names(self):
        r = self.check("parameter width = 8;\nchild wrong_name(.some_VENDOR_PORT(data_i));")
        self.assertEqual(2, len(self.violations(r, "NAME-001")))

    def test_vendor_port_labels_unrestricted(self):
        self.assertEqual([], self.check("VENDOR_IP u_memory(.DOUT(data_o), .CLK(clk));")["diagnostics"])

    def test_positional_port_and_parameter(self):
        r = self.check("child #(8) u_child(clk, data_i, data_o);")
        self.assertTrue(self.violations(r, "INST-001"))

    def test_explicit_sensitivity_list(self):
        r = self.check("reg data_wire;\nalways @(data_i) begin\n data_wire = data_i;\nend")
        self.assertTrue(self.violations(r, "PROC-002"))

    def test_if_else_and_case_blocks(self):
        r = self.check("""always @(*) begin
    if (data_i) data_o = 1'b0;
    else data_o = 1'b1;
    case (data_i)
        default: data_o = 1'b0;
    endcase
end""")
        self.assertEqual(3, len(self.violations(r, "BLOCK-001")))

    def test_case_default(self):
        r = self.check("always @(*) begin\ncase (data_i)\n1'b0: begin\ndata_o = 1'b0;\nend\nendcase\nend")
        self.assertTrue(self.violations(r, "CASE-001"))

    def test_multiple_register_writers_including_slices(self):
        r = self.check("""reg [1:0] data_reg;
always @(posedge clk) begin
    data_reg[0] <= data_i;
end
always @(posedge clk) begin
    data_reg[1] <= data_i;
end""")
        self.assertTrue(self.violations(r, "DRIVER-001"))

    def test_array_multiple_writers_require_review(self):
        r = self.check("""reg [7:0] data_reg [0:7];
always @(posedge clk) begin
    data_reg[0] <= 8'd0;
end
always @(posedge clk) begin
    data_reg[1] <= 8'd1;
end""")
        self.assertFalse(self.violations(r, "DRIVER-001"))
        self.assertIn("DRIVER-001", r["unchecked_rules"])

    def test_fsm_state_process_separated(self):
        r = self.check(FSM.replace("state_reg <= next_state_wire;", "state_reg <= next_state_wire;\n        data_o <= data_i;"))
        self.assertTrue(self.violations(r, "FSM-001"))

    def test_fsm_next_state_process_separated(self):
        r = self.check(FSM.replace("next_state_wire = state_reg;", "next_state_wire = state_reg;\n    data_o = data_i;"))
        self.assertTrue(self.violations(r, "FSM-001"))

    def test_fsm_default_first(self):
        r = self.check(FSM.replace("next_state_wire = state_reg;", "next_state_wire = ST_IDLE;"))
        self.assertTrue(self.violations(r, "FSM-001"))

    def test_no_event_control_does_not_crash(self):
        r = self.check(FSM.replace("always @(*)", "always"))
        self.assertTrue(self.violations(r, "PROC-002"))

    def test_integer_state_parameter_does_not_crash(self):
        r = self.check(FSM.replace("localparam [1:0] ST_IDLE", "localparam integer ST_IDLE"))
        self.assertTrue(self.violations(r, "FSM-002"))

    def test_state_register_samples_next_state(self):
        r = self.check(FSM.replace("state_reg <= next_state_wire;", "state_reg <= ST_RUN;"))
        self.assertTrue(self.violations(r, "FSM-001"))

    def test_fsm_named_sized_states(self):
        for change in (FSM.replace("next_state_wire = ST_RUN;", "next_state_wire = 2'd1;"),
                       FSM.replace("localparam [1:0] ST_RUN", "localparam ST_RUN")):
            with self.subTest(change=change):
                self.assertTrue(self.violations(self.check(change), "FSM-002"))

    def test_fsm_casez(self):
        self.assertTrue(self.violations(self.check(FSM.replace("case (state_reg)", "casez (state_reg)")), "FSM-002"))

    def test_fsm_case_labels_named(self):
        self.assertTrue(self.violations(self.check(FSM.replace("ST_IDLE: begin", "2'd0: begin")), "FSM-002"))

    def test_internal_wire_role_suffix(self):
        self.assertTrue(self.violations(self.check("wire temporary;"), "NAME-001"))

    def test_generated_multiwriter_is_incomplete_not_definite_failure(self):
        r = self.check("""reg data_reg;
generate
    if (1) begin: gen_a
        always @(posedge clk) begin
            data_reg <= data_i;
        end
    end else begin: gen_b
        always @(posedge clk) begin
            data_reg <= data_i;
        end
    end
endgenerate""")
        self.assertFalse(self.violations(r, "DRIVER-001"))
        self.assertIn("DRIVER-001", r["unchecked_rules"])

    def test_generated_fsm_does_not_merge_scopes(self):
        r = self.check("generate if (1) begin: gen_a\n" + FSM + "end endgenerate")
        self.assertFalse(self.violations(r, "FSM-001"))
        self.assertIn("FSM-001", r["unchecked_rules"])

    def test_missing_next_state(self):
        self.assertTrue(self.violations(self.check("reg state_reg;"), "FSM-001"))

    def test_preprocessing_incomplete_and_no_include_read(self):
        for prefix in ('`include "does-not-exist.vh"\n', "`define A 1\n", "`ifdef FLAG\n"):
            r = checker.check_source("test.v", prefix + wrap(""))
            self.assertEqual(list(checker.RULES), r["unchecked_rules"])
            self.assertEqual("incomplete", r["diagnostics"][0]["kind"])

    def test_comments_and_strings_do_not_trigger_preprocessing(self):
        r = self.check('// `include "missing.vh"\ninitial $display("`ifdef X");')
        self.assertEqual([], r["diagnostics"])

    def test_broken_syntax_incomplete(self):
        r = checker.check_source("test.v", "module test(; endmodule")
        self.assertEqual(list(checker.RULES), r["unchecked_rules"])

    def test_missing_parser_incomplete(self):
        with patch.object(checker, "_load_parser", side_effect=ImportError("dependency missing")):
            r = self.check("")
        self.assertEqual(list(checker.RULES), r["unchecked_rules"])
        self.assertIn("dependency missing", r["diagnostics"][0]["message"])

    def test_header_not_a_module(self):
        r = checker.check_source("test.vh", "localparam WIDTH=8;")
        self.assertEqual(list(checker.RULES), r["unchecked_rules"])

    def test_multiple_signals_in_declaration(self):
        r = self.check("reg data_reg, extra_reg;\nalways @(posedge clk) begin\ndata_reg <= data_i;\nextra_reg <= data_i;\nend")
        self.assertEqual(1, len(self.violations(r, "DECL-001")))


if __name__ == "__main__":
    unittest.main()

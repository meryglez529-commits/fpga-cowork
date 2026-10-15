"""Deterministic syntax checks for fpga-cowork's Verilog style.

Uses pyslang 12.0.0 concrete syntax, without elaboration, include expansion, or
hardware inference. Install the pinned wheel and nanobind-backend into the
isolated dependency directory; the hook never installs packages. Unavailable
parsing or unsupported preprocessing is explicitly incomplete, never a pass.
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

RULES = (
    "PARSE-001", "PORT-001", "NAME-001", "INST-001", "PROC-001",
    "PROC-002", "BLOCK-001", "CASE-001", "DRIVER-001", "FSM-001",
    "FSM-002", "DECL-001", "DECL-002",
)
PINNED_VERSION = "12.0.0"
LOWER = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
UPPER = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
STATE = re.compile(r"(?:[a-z][a-z0-9_]*_)?state_reg\Z")


def _control_name(name):
    return (name == "clk" or name.startswith("clk_")
            or name == "rst_n" or name.startswith("rst_n_")) and not name.endswith(
                ("_i", "_o", "_io", "_reg", "_wire"))


def _load_parser():
    dep = os.environ.get("FPGA_COWORK_PYSLANG_PATH")
    if not dep:
        dep = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
                  / "fpga-cowork" / "python-deps" / "pyslang-12.0.0")
    if Path(dep).is_dir() and dep not in sys.path:
        sys.path.insert(0, dep)
    import pyslang
    if pyslang.__version__ != PINNED_VERSION:
        raise ImportError("Expected pyslang 12.0.0; found " + pyslang.__version__)
    return pyslang


def _kind(node):
    return str(getattr(node, "kind", "")).split(".")[-1]


def _nodes(node):
    if not hasattr(node, "sourceRange"):
        return
    yield node
    for child in node:
        yield from _nodes(child)


def _name(token):
    return getattr(token, "valueText", str(token).strip())


def _targets(expr):
    kind = _kind(expr)
    if kind in {"IdentifierName", "IdentifierSelectName"}:
        return {_name(expr.identifier)}
    if kind == "ConcatenationExpression":
        return set().union(*(_targets(n) for n in expr.expressions
                             if hasattr(n, "sourceRange")))
    return set()


def _ancestor(node, kinds):
    node = node.parent
    while node is not None:
        if _kind(node) in kinds:
            return node
        node = node.parent
    return None


def _is_assignment(node):
    return _kind(node) in {"AssignmentExpression", "NonblockingAssignmentExpression"}


def _loop_control(node):
    """Only assignments in a for header are exempt, not its body."""
    current = node
    while current.parent is not None:
        parent = current.parent
        if _kind(parent) == "ForLoopStatement":
            return current is not parent.statement and current != parent.statement
        current = parent
    return False


def _existing_ports(slang, options, path, text):
    """Read only directly parsed baseline port names, module names and directions."""
    from check_rtl import lex
    tokens, _, error = lex(text)
    if error or any(token.kind == "macro" or
                    (token.kind == "directive" and token.value not in
                     {"timescale", "default_nettype"}) for token in tokens):
        return None
    tree = slang.syntax.SyntaxTree.fromText(
        text, slang.SourceManager(), name=Path(path).name, options=options)
    if any(diagnostic.isError() for diagnostic in tree.diagnostics):
        return None
    ports = set()
    for module in (node for node in _nodes(tree.root) if _kind(node) == "ModuleDeclaration"):
        if module.header.ports is not None and _kind(module.header.ports) != "AnsiPortList":
            return None
        for node in _nodes(module):
            if _kind(node) == "ImplicitAnsiPort":
                if node.header is None or not _name(node.header.direction):
                    return None
                ports.add((_name(module.header.name), _name(node.declarator.name),
                           _name(node.header.direction)))
    return ports


def check_source(path, text, preprocessor_checked=False, existing_text=None):
    result = {"checked_rules": [], "unchecked_rules": [], "diagnostics": [], "notes": []}

    def add(rule, line, message, kind="violation", reviewable=False):
        item = {"path": str(path), "line": max(1, int(line)), "rule_id": rule,
                "kind": kind, "message": message}
        if reviewable:
            item["reviewable"] = True
        if item not in result["diagnostics"]:
            result["diagnostics"].append(item)

    def incomplete(message, line=1, reviewable=False):
        result["unchecked_rules"] = list(RULES)
        add("PARSE-001", line, message, "incomplete", reviewable=reviewable)
        return result

    if Path(path).suffix.lower() != ".v":
        return incomplete("Header fragments are not parsed as standalone RTL modules.")
    if not preprocessor_checked:
        # Reuse the existing lexer, which distinguishes comments and strings.
        # Function-local import avoids an import cycle with the report builder.
        from check_rtl import lex
        tokens, _, error = lex(text)
        if error:
            return incomplete("Lexical error prevents structural checks.", error[0])
        blocked = next((t for t in tokens if t.kind == "macro" or
                        (t.kind == "directive" and t.value not in
                         {"timescale", "default_nettype"})), None)
        if blocked:
            return incomplete("Structural checks require direct source: preprocessing "
                              "is not expanded or silently limited to an active branch.", blocked.line,
                              reviewable=True)
    try:
        slang = _load_parser()
        parser_options = slang.parsing.ParserOptions()
        parser_options.languageVersion = slang.LanguageVersion.v1364_2005
        pp_options = slang.parsing.PreprocessorOptions()
        pp_options.languageVersion = slang.LanguageVersion.v1364_2005
        tree = slang.syntax.SyntaxTree.fromText(
            text, slang.SourceManager(), name=Path(path).name,
            options=slang.Bag([parser_options, pp_options]))
    except Exception as exc:
        return incomplete("Verilog parser unavailable: " + str(exc))
    errors = [d for d in tree.diagnostics if d.isError()]
    if errors:
        for diagnostic in errors[:8]:
            add("PARSE-001", tree.sourceManager.getLineNumber(diagnostic.location),
                str(diagnostic.code) + ": Verilog syntax/preprocessing could not be parsed.",
                "incomplete")
        result["unchecked_rules"] = list(RULES)
        result["notes"].append(slang.DiagnosticEngine.reportAll(tree.sourceManager, tree.diagnostics))
        return result
    result["checked_rules"] = list(RULES)
    result["notes"].append("pyslang 12.0.0 syntax only (Verilog-2005 parser); full Verilog-2001 "
                           "conformance, elaboration, widths, FSM behavior and registered-output "
                           "provenance still require the standards review.")
    sm = tree.sourceManager
    existing_ports = (_existing_ports(slang, slang.Bag([parser_options, pp_options]), path,
                                      existing_text) if existing_text is not None else set())

    def line(node):
        return sm.getLineNumber(node.sourceRange.start)

    def complain(rule, node, message, kind="violation"):
        add(rule, line(node), message, kind, reviewable=(kind == "incomplete"))
        if kind == "incomplete" and rule in result["checked_rules"]:
            result["checked_rules"].remove(rule)
            result["unchecked_rules"].append(rule)

    all_nodes = list(_nodes(tree.root))
    modules = [n for n in all_nodes if _kind(n) == "ModuleDeclaration"]
    if not modules:
        return incomplete("No module declaration was parsed.")
    for module in modules:
        nodes = [n for n in _nodes(module)
                 if n == module or _ancestor(n, {"ModuleDeclaration"}) == module]
        ports = {}
        declarations = {}
        memories = set()
        params = {}
        module_name = _name(module.header.name)
        if not LOWER.fullmatch(module_name):
            complain("NAME-001", module, "Module names use lower_snake_case.")
        port_list = module.header.ports
        if port_list is not None and _kind(port_list) != "AnsiPortList":
            complain("PORT-001", port_list, "Use ANSI ports with explicit direction and wire/reg type.")
        for node in nodes:
            kind = _kind(node)
            if kind == "ImplicitAnsiPort":
                name = _name(node.declarator.name)
                header = node.header
                direction = _name(header.direction) if header is not None else ""
                ports[name] = direction
                suffix = {"input": "_i", "output": "_o", "inout": "_io"}.get(direction)
                explicit = (header is not None and
                            ((_kind(header) == "NetPortHeader" and bool(_name(header.netType)))
                             or (_kind(header) == "VariablePortHeader"
                                 and _kind(header.dataType) == "RegType")))
                if not suffix or not explicit:
                    complain("PORT-001", node, "Each ANSI port explicitly declares direction and wire/reg type.")
                if suffix:
                    valid_name = LOWER.fullmatch(name) and (
                        _control_name(name) or (name.endswith(suffix)
                        and not name.endswith(("_reg" + suffix, "_wire" + suffix))
                        and not name.startswith(("clk_", "rst_n_"))))
                    preserved = (existing_ports is not None and
                                 (module_name, name, direction) in existing_ports)
                    if not valid_name and not preserved:
                        complain("PORT-001", node, "Port " + name + " uses " + suffix
                                 + "; clocks/resets use clk/rst_n with optional domain names. "
                                 "Do not stack internal _reg/_wire suffixes on ports.",
                                 "incomplete" if existing_ports is None else "violation")
            elif kind in {"DataDeclaration", "NetDeclaration", "ParameterDeclaration"}:
                decls = [d for d in node.declarators if _kind(d) == "Declarator"]
                # Function locals are checked only for general naming, not hardware roles.
                for d in decls:
                    name = _name(d.name)
                    if kind == "ParameterDeclaration":
                        params[name] = node
                        if not UPPER.fullmatch(name):
                            complain("NAME-001", d, "Parameter/localparam " + name + " uses UPPER_SNAKE_CASE.")
                    elif _ancestor(node, {"FunctionDeclaration", "TaskDeclaration"}) is None:
                        declarations[name] = d
                        if len(d.dimensions):
                            memories.add(name)
                        if not LOWER.fullmatch(name):
                            complain("NAME-001", d, "Signal " + name + " uses lower_snake_case.")
                        data_type = getattr(node, "type", None)
                        if (_kind(data_type) != "IntegerType" and not _control_name(name)
                                and not name.endswith(("_reg", "_wire"))):
                            complain("NAME-001", d, "Internal signal " + name +
                                     " needs its circuit-role suffix (_reg/_wire).")
                    if kind == "NetDeclaration" and d.initializer is not None:
                        complain("DECL-002", d, "Declare wires separately; use assign in the logic section.")
                if kind != "ParameterDeclaration" and len(decls) > 1:
                    complain("DECL-001", node, "Declare one signal per declaration.")
            elif kind == "FunctionDeclaration":
                name = _name(node.prototype.name)
                if not LOWER.fullmatch(name):
                    complain("NAME-001", node, "Function names use lower_snake_case.")
            elif kind == "GenerateBlock":
                name = _name(node.label.name) if node.label is not None else ""
                if not name.startswith("gen_") or not LOWER.fullmatch(name):
                    complain("NAME-001", node, "Generate blocks use gen_<purpose> labels.")
            elif kind == "HierarchicalInstance":
                name = _name(node.decl.name) if node.decl is not None else ""
                if not name.startswith("u_") or not LOWER.fullmatch(name):
                    complain("NAME-001", node, "Module instance names use u_<purpose>.")
            elif kind in {"OrderedPortConnection", "OrderedParamAssignment", "WildcardPortConnection"}:
                complain("INST-001", node, "Use explicit named port connections and named parameter overrides.")
            elif kind == "ConditionalStatement":
                if _kind(node.statement) != "SequentialBlockStatement":
                    complain("BLOCK-001", node.statement, "if bodies require begin/end.")
                if node.elseClause is not None and _kind(node.elseClause.clause) not in {
                    "SequentialBlockStatement", "ConditionalStatement"}:
                    complain("BLOCK-001", node.elseClause, "else bodies require begin/end.")
            elif kind in {"StandardCaseItem", "DefaultCaseItem"}:
                if _kind(node.clause) != "SequentialBlockStatement":
                    complain("BLOCK-001", node.clause, "case items require begin/end.")
            elif kind in {"ForLoopStatement", "WhileLoopStatement", "RepeatLoopStatement", "ForeverLoopStatement"}:
                if _kind(node.statement) != "SequentialBlockStatement":
                    complain("BLOCK-001", node.statement, "Loop bodies require begin/end.")
            elif kind == "CaseStatement":
                if not any(_kind(i) == "DefaultCaseItem" for i in node.items):
                    complain("CASE-001", node, "case requires an explicit default branch.")
                if _name(node.caseKeyword) == "casex":
                    complain("CASE-001", node, "Do not use casex; use case or intentional casez decoding.")

        processes = []
        writers = defaultdict(set)
        writer_nodes = defaultdict(list)
        for node in nodes:
            if _kind(node) != "AlwaysBlock":
                continue
            statement = node.statement
            timing = statement.timingControl if _kind(statement) == "TimingControlStatement" else None
            sequential = timing is not None and any(
                _kind(n) == "SignalEventExpression" and _name(n.edge) in {"posedge", "negedge"}
                for n in _nodes(timing))
            if not sequential and (_kind(timing) != "ImplicitEventControl"
                                   or re.sub(r"\s+", "", str(timing)) != "@(*)"):
                complain("PROC-002", node, "Combinational processes use always @(*).")
            if sequential:
                clocks = set()
                for event in _nodes(timing):
                    if _kind(event) == "SignalEventExpression":
                        clocks.update(name for name in _targets(event.expr)
                                       if "rst" not in name.lower().split("_"))
                if len(clocks) > 1:
                    if sum("clk" in name.lower().split("_") for name in clocks) > 1:
                        complain("PROC-002", node, "Each process uses one working clock.")
                    else:
                        complain("PROC-002", node, "Clock/reset roles need review: "
                                 + ", ".join(sorted(clocks)), "incomplete")
            assignments = [a for a in _nodes(statement) if _is_assignment(a) and not _loop_control(a)]
            targets = set()
            pid = len(processes)
            for assignment in assignments:
                names = _targets(assignment.left)
                if not names:
                    complain("DRIVER-001", assignment, "Assignment target needs semantic resolution.", "incomplete")
                targets.update(names)
                correct = "NonblockingAssignmentExpression" if sequential else "AssignmentExpression"
                if _kind(assignment) != correct:
                    complain("PROC-001", assignment, "Clocked state uses <=; combinational results use =.")
                for name in names:
                    writers[name].add(pid)
                    writer_nodes[name].append(node)
                    if name in ports or _control_name(name):
                        continue
                    suffixes = ("_reg",) if sequential else ("_wire",)
                    if not name.endswith(suffixes):
                        complain("NAME-001", assignment, name + " must end with " + "/".join(suffixes)
                                 + " for this assignment process.")
            processes.append({"node": node, "sequential": sequential,
                              "assignments": assignments, "targets": targets})
        for assignment in (n for n in nodes if _is_assignment(n)):
            owner = _ancestor(assignment, {"ContinuousAssign"})
            if owner is not None:
                for name in _targets(assignment.left):
                    writers[name].add(("assign", id(owner)))
                    writer_nodes[name].append(owner)
        for name, owners in writers.items():
            if len(owners) > 1:
                generated = any(_ancestor(n, {"LoopGenerate", "IfGenerate", "CaseGenerate"})
                                is not None for n in writer_nodes[name])
                complain("DRIVER-001", writer_nodes[name][-1], "Signal " + name +
                         " has multiple always/assign drivers." +
                         (" Generate exclusivity requires elaboration." if generated else "") +
                         (" Array indices and write-port ownership require review." if name in memories else ""),
                         "incomplete" if generated or name in memories else "violation")

        for state_reg in sorted(n for n in declarations if STATE.fullmatch(n)):
            next_state_wire = state_reg[:-len("state_reg")] + "next_state_wire"
            if _ancestor(declarations[state_reg], {"GenerateBlock", "LoopGenerate", "IfGenerate", "CaseGenerate"}) is not None:
                complain("FSM-001", declarations[state_reg], "FSM declarations in generate scopes require "
                         "scope/elaboration review; no merged state identity is inferred.", "incomplete")
                complain("FSM-002", declarations[state_reg], "Generated FSM state values require scope review.", "incomplete")
                continue
            if next_state_wire not in declarations:
                complain("FSM-001", declarations[state_reg], state_reg + " needs a corresponding " + next_state_wire + ".")
                continue
            state_processes = [p for p in processes if state_reg in p["targets"]]
            next_processes = [p for p in processes if next_state_wire in p["targets"]]
            if len(state_processes) != 1 or not state_processes[0]["sequential"]:
                complain("FSM-001", declarations[state_reg], "Current state must have one dedicated clocked process.")
            elif state_processes[0]["targets"] != {state_reg}:
                complain("FSM-001", state_processes[0]["node"], "State-register process only updates " + state_reg + ".")
            elif not any(_kind(a.right) == "IdentifierName" and _name(a.right.identifier) == next_state_wire
                         for a in state_processes[0]["assignments"]):
                complain("FSM-001", state_processes[0]["node"], "State-register process must sample " + next_state_wire + ".")
            if len(next_processes) != 1 or next_processes[0]["sequential"]:
                complain("FSM-001", declarations[next_state_wire], "Next state must have one combinational transition process.")
                continue
            process = next_processes[0]
            if process["targets"] != {next_state_wire}:
                complain("FSM-001", process["node"], "Next-state process must not also update datapath or outputs.")
            body = process["node"].statement
            if _kind(body) == "TimingControlStatement":
                body = body.statement
            items = list(body.items) if _kind(body) == "SequentialBlockStatement" else [body]
            first = items[0] if items else None
            first_expr = first.expr if _kind(first) == "ExpressionStatement" else None
            if not (_is_assignment(first_expr) and _targets(first_expr.left) == {next_state_wire}
                    and _kind(first_expr.right) == "IdentifierName"
                    and _name(first_expr.right.identifier) == state_reg):
                complain("FSM-001", process["node"], "Start the next-state block with " + next_state_wire + " = " + state_reg + ".")
            for process in state_processes + next_processes:
                for assignment in process["assignments"]:
                    if not _targets(assignment.left) & {state_reg, next_state_wire}:
                        continue
                    right = assignment.right
                    if _kind(right) == "IdentifierName":
                        value = _name(right.identifier)
                        if value in {state_reg, next_state_wire}:
                            continue
                        param = params.get(value)
                        if (param is None or _name(param.keyword) != "localparam"
                                or not len(getattr(param.type, "dimensions", ()))
                                or not re.fullmatch(r"(?:[A-Z][A-Z0-9_]*_)?ST_[A-Z0-9_]+", value)):
                            complain("FSM-002", assignment, "State values use named, explicitly sized localparams.")
                    else:
                        complain("FSM-002", assignment, "State assignments use a named state localparam or state_reg/next_state_wire.")
            for case in (n for n in _nodes(next_processes[0]["node"]) if _kind(n) == "CaseStatement"):
                if _targets(case.expr) != {state_reg}:
                    continue
                if _name(case.caseKeyword) != "case":
                    complain("FSM-002", case, "State decoding uses ordinary case, never casex/casez.")
                for item in case.items:
                    if _kind(item) != "StandardCaseItem":
                        continue
                    for expr in item.expressions:
                        if not hasattr(expr, "sourceRange"):
                            continue
                        value = _name(expr.identifier) if _kind(expr) == "IdentifierName" else ""
                        param = params.get(value)
                        if (param is None or _name(param.keyword) != "localparam"
                                or not len(getattr(param.type, "dimensions", ()))
                                or not re.fullmatch(r"(?:[A-Z][A-Z0-9_]*_)?ST_[A-Z0-9_]+", value)):
                            complain("FSM-002", expr, "State case labels use named, explicitly sized ST_ localparams.")
    return result

#!/usr/bin/env python3
"""Check deterministic source and parsed-structure RTL coding rules.

Usage: python check_rtl.py [--format text|json] FILE [FILE ...]
Explicit .v/.vh inputs only; no source rewriting. Physical format and direct
lexical rules apply to both. Direct .v source also uses pinned pyslang CST;
macro/include/conditional structure remains an explicit reviewable limitation.
Header fragments are reviewed in their include context by the standards review.

Comments, strings and directive bodies are distinguished from executable code.
SYN-002 identifies explicit synthesis hints for review, not definite violations.
Parser errors/unavailability and bad input are incomplete execution, not
reviewable limitations. See references/rtl-checks.md for exact rule coverage.

Exit 0: covered machine checks passed; 1: definite violations; 2: bad input or
any incomplete implemented check (also retaining definite violations). A machine
pass does not replace the required AI review against the full coding standard.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


FORMAT_RULES = ("FMT-002", "FMT-003", "FMT-004", "FMT-005")
STRUCTURE_RULES = ("FILE-001",)
SYNTAX_RULES = ("SYN-001", "SYN-002")
from rtl_structure import RULES as AST_RULES, check_source

ALL_RULES = FORMAT_RULES + STRUCTURE_RULES + SYNTAX_RULES + AST_RULES
CONDITIONALS = {"ifdef", "ifndef", "elsif", "else", "endif"}
DIRECTIVES = CONDITIONALS | {
    "define", "undef", "include", "timescale", "default_nettype", "resetall",
    "celldefine", "endcelldefine", "unconnected_drive", "nounconnected_drive",
    "line", "pragma", "begin_keywords", "end_keywords", "undefineall",
}
HINTS = {"full_case", "parallel_case"}
IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
MODULE_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
NUMBER = re.compile(
    r"(?:[0-9][0-9_]*\s*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+"
    r"|'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+"
    r"|[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9_]+)?)"
)
UNCOVERED = [
    "Preprocessor expansion, macro-definition bodies and include targets",
    "Full Verilog-2001 language conformance, compilation and elaboration",
    "Semantic coding checks: widths, combinational assignment coverage and parameter bounds",
    "Functional correctness, protocol/CDC behavior, resource selection and timing",
    "Style rules not listed in implemented_rules, including indentation, organization and comments",
]


@dataclass
class Token:
    kind: str
    value: str
    line: int
    offset: int
    end: int


@dataclass
class Comment:
    text: str
    line: int
    offset: int


@dataclass
class FileResult:
    path: str
    applicable_rules: List[str]
    diagnostics: List[dict] = field(default_factory=list)
    unchecked: set = field(default_factory=set)
    notes: List[str] = field(default_factory=list)

    def add(self, rule_id: str, line: int, kind: str, message: str) -> None:
        self.diagnostics.append({
            "path": self.path,
            "line": max(1, line),
            "rule_id": rule_id,
            "kind": kind,
            "message": message,
        })

    def incomplete(self, rules: Sequence[str], line: int, message: str,
                   rule_id: str = "CHECK-002", reviewable: bool = False) -> None:
        self.unchecked.update(rules)
        self.add(rule_id, line, "incomplete", message)
        if reviewable:
            self.diagnostics[-1]["reviewable"] = True

    def as_dict(self) -> dict:
        kinds = {item["kind"] for item in self.diagnostics}
        if self.unchecked or kinds & {"incomplete", "input_error"}:
            status = "incomplete"
        elif "violation" in kinds:
            status = "fail"
        else:
            status = "pass"
        return {
            "path": self.path,
            "status": status,
            "checked_rules": [r for r in self.applicable_rules if r not in self.unchecked],
            "unchecked_rules": [r for r in self.applicable_rules if r in self.unchecked],
            "diagnostics": sorted(self.diagnostics, key=lambda d: (d["line"], d["rule_id"])),
            "notes": self.notes,
        }


def _logical_line_end(text: str, start: int) -> int:
    """Skip a define body without leaking its comments into ordinary code."""
    pos = start
    quoted = False
    while pos < len(text):
        if text[pos] == "\n":
            if pos > start and text[pos - 1] == "\\":
                pos += 1
                continue
            return pos
        if quoted:
            if text[pos] == "\\" and pos + 1 < len(text) and text[pos + 1] != "\n":
                pos += 2
                continue
            if text[pos] == '"':
                quoted = False
        elif text[pos] == '"':
            quoted = True
        elif text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            if end < 0:
                raise ValueError("Unterminated block comment in macro definition; lexical checks incomplete.")
            pos = end + 2
            continue
        elif text.startswith("//", pos):
            end = text.find("\n", pos + 2)
            pos = len(text) if end < 0 else end
            continue
        pos += 1
    return len(text)


def lex(text: str) -> Tuple[List[Token], List[Comment], Optional[Tuple[int, str]]]:
    """Return physical-line tokens/comments, or an incomplete lexical scan."""
    tokens = []
    comments = []
    pos = 0
    line = 1
    size = len(text)
    while pos < size:
        ch = text[pos]
        if ch.isspace():
            line += ch == "\n"
            pos += 1
            continue
        start, start_line = pos, line
        if text.startswith("//", pos):
            end = text.find("\n", pos + 2)
            end = size if end < 0 else end
            comments.append(Comment(text[pos + 2:end], line, pos))
            pos = end
            continue
        if text.startswith("/*", pos):
            end = text.find("*/", pos + 2)
            if end < 0:
                return tokens, comments, (line, "Unterminated block comment; lexical checks incomplete.")
            comments.append(Comment(text[pos + 2:end], line, pos))
            end += 2
            line += text[pos:end].count("\n")
            pos = end
            continue
        if ch == '"':
            pos += 1
            while pos < size:
                if text[pos] == "\\":
                    if pos + 1 < size:
                        line += text[pos + 1] == "\n"
                    pos += 2
                elif text[pos] == '"':
                    pos += 1
                    tokens.append(Token("string", text[start:pos], start_line, start, pos))
                    break
                elif text[pos] == "\n":
                    return tokens, comments, (start_line, "Unterminated string; lexical checks incomplete.")
                else:
                    pos += 1
            else:
                return tokens, comments, (start_line, "Unterminated string; lexical checks incomplete.")
            continue
        if ch == "\\":
            pos += 1
            while pos < size and not text[pos].isspace():
                pos += 1
            tokens.append(Token("escaped_identifier", text[start + 1:pos], line, start, pos))
            continue
        if ch == "`":
            match = IDENTIFIER.match(text, pos + 1)
            if match is None:
                return tokens, comments, (line, "Unrecognized backtick construct; lexical checks incomplete.")
            name = match.group()
            pos = match.end()
            kind = "directive" if name in DIRECTIVES else "macro"
            tokens.append(Token(kind, name, line, start, pos))
            if name == "define":
                try:
                    end = _logical_line_end(text, pos)
                except ValueError as error:
                    return tokens, comments, (line, str(error))
                line += text[pos:end].count("\n")
                pos = end
            continue
        match = IDENTIFIER.match(text, pos)
        if match is not None:
            pos = match.end()
            tokens.append(Token("identifier", match.group(), line, start, pos))
            continue
        match = NUMBER.match(text, pos)
        if match is not None:
            pos = match.end()
            line += text[start:pos].count("\n")
            tokens.append(Token("number", match.group(), start_line, start, pos))
            continue
        symbol = text[pos:pos + 2] if text[pos:pos + 2] in {"(*", "*)"} else ch
        pos += len(symbol)
        tokens.append(Token("symbol", symbol, line, start, pos))
    # A macro name in a directive is not a Verilog keyword. In particular,
    # `ifndef defparam must not be mistaken for a defparam statement. A macro
    # used as an include filename is likewise not a top-level module macro.
    for index, token in enumerate(tokens[:-1]):
        if token.kind != "directive":
            continue
        following = tokens[index + 1]
        if token.value in {"undef", "ifdef", "ifndef", "elsif"}:
            if following.kind in {"identifier", "macro", "escaped_identifier"}:
                following.kind = "directive_argument"
        elif token.value == "include" and following.kind == "macro":
            following.kind = "directive_argument"
    return tokens, comments, None


def check_format(text: str, result: FileResult) -> None:
    for line_number, content in enumerate(text.split("\n"), 1):
        if "\t" in content:
            result.add("FMT-002", line_number, "violation", "Tab character is forbidden.")
        if content and content[-1].isspace():
            result.add("FMT-003", line_number, "violation", "Trailing whitespace is forbidden.")
        if len(content) > 100:
            result.add("FMT-005", line_number, "violation", "Lines must not exceed 100 characters.")
    if text and not text.endswith("\n"):
        result.add("FMT-004", text.count("\n") + 1, "violation", "Nonempty file must end with a newline.")


def _hint(result: FileResult, line: int, name: str) -> None:
    result.incomplete(
        ("SYN-002",), line,
        "Explicit {} hint requires manual review: lexical scanning cannot determine "
        "whether it hides incomplete branches.".format(name), "SYN-002",
        reviewable=True,
    )


def check_syntax(tokens: Sequence[Token], comments: Sequence[Comment],
                 result: FileResult) -> None:
    for token in tokens:
        if token.kind == "identifier" and token.value == "defparam":
            result.add("SYN-001", token.line, "violation", "Direct defparam statement is forbidden.")

    # Only an explicit pragma leader is meaningful; prose mentioning a hint is not.
    pragma = re.compile(r"\A\s*(?:(?:synopsys|synthesis)\s+|pragma\s+(?:(?:synopsys|synthesis)\s+)?)")
    for comment in comments:
        match = pragma.match(comment.text)
        if match is None:
            continue
        remaining = comment.text[match.end():]
        first = re.match(r"(full_case|parallel_case)\b", remaining)
        if first is None:
            continue
        for hint in re.finditer(r"\b(full_case|parallel_case)\b", remaining):
            line = comment.line + comment.text[:match.end() + hint.start()].count("\n")
            _hint(result, line, hint.group())

    in_attribute = False
    name_expected = False
    nested = 0
    for index, token in enumerate(tokens):
        if token.kind == "symbol" and token.value == "(*":
            in_attribute, name_expected, nested = True, True, 0
            continue
        if in_attribute:
            if token.kind == "symbol" and token.value == "*)":
                in_attribute = False
                continue
            if token.kind == "symbol" and token.value in {"(", "[", "{"}:
                nested += 1
            elif token.kind == "symbol" and token.value in {")", "]", "}"}:
                nested -= 1
            elif nested == 0 and token.kind == "symbol" and token.value == ",":
                name_expected = True
            elif nested == 0 and name_expected and token.kind == "identifier":
                if token.value in HINTS:
                    _hint(result, token.line, token.value)
                name_expected = False
        if token.kind == "directive" and token.value == "pragma":
            args = []
            for following in tokens[index + 1:]:
                if following.line != token.line or following.kind == "directive":
                    break
                args.append(following)
            if args and args[0].value in {"synthesis", "synopsys"}:
                args = args[1:]
            if args and args[0].kind == "identifier" and args[0].value in HINTS:
                for arg in args:
                    if arg.kind == "identifier" and arg.value in HINTS:
                        _hint(result, arg.line, arg.value)


def check_structure(tokens: Sequence[Token], result: FileResult, stem: str) -> None:
    conditional = next((t for t in tokens if t.kind == "directive" and t.value in CONDITIONALS), None)
    if conditional is not None:
        result.incomplete(STRUCTURE_RULES, conditional.line,
                          "Conditional compilation prevents source-only module checks; "
                          "inspect all source branches in the standards review.", reviewable=True)
        return

    depth = 0
    for index, token in enumerate(tokens):
        if token.kind == "identifier" and token.value in {"module", "macromodule"}:
            depth += 1
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            if following is not None and following.kind == "macro":
                result.incomplete(STRUCTURE_RULES, following.line,
                                  "Macro-generated module name cannot be checked without expansion.",
                                  reviewable=True)
                return
        elif token.kind == "identifier" and token.value == "endmodule":
            depth = max(0, depth - 1)
        elif token.kind == "macro" and depth == 0:
            result.incomplete(STRUCTURE_RULES, token.line,
                              "Top-level macro may generate module structure; expansion is not covered.",
                              reviewable=True)
            return

    modules = [(i, t) for i, t in enumerate(tokens)
               if t.kind == "identifier" and t.value in {"module", "macromodule"}]
    ends = [t for t in tokens if t.kind == "identifier" and t.value == "endmodule"]
    if len(modules) != 1 or len(ends) != 1:
        line = modules[1][1].line if len(modules) > 1 else 1
        result.add("FILE-001", line, "violation",
                   "A .v file must contain exactly one directly written module and one endmodule "
                   "(found {} and {}).".format(len(modules), len(ends)))
    for index, token in modules:
        name = tokens[index + 1] if index + 1 < len(tokens) else None
        if name is None or name.kind not in {"identifier", "escaped_identifier"}:
            result.add("FILE-001", token.line, "violation", "Module has no directly written identifier.")
        elif not MODULE_NAME.fullmatch(name.value) or name.value != stem:
            result.add("FILE-001", name.line, "violation",
                       "Module name {!r} must match file stem {!r} and use lowercase "
                       "letters, digits and underscores, without a leading digit.".format(name.value, stem))

def check_file(filename: str, existing_text=None) -> dict:
    path = Path(filename).expanduser().absolute()
    suffix = path.suffix.lower()
    applicable = list(FORMAT_RULES + (STRUCTURE_RULES if suffix == ".v" else ())
                      + SYNTAX_RULES + (AST_RULES if suffix == ".v" else ()))
    result = FileResult(str(path), applicable)
    if suffix not in {".v", ".vh"}:
        result.unchecked.update(applicable)
        result.add("INPUT-001", 1, "input_error", "Only explicit .v or .vh files are accepted.")
        return result.as_dict()
    try:
        raw = path.read_bytes()
    except (OSError, ValueError) as error:
        result.unchecked.update(applicable)
        result.add("INPUT-001", 1, "input_error", "Cannot read file: {}".format(error))
        return result.as_dict()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    decode_error = None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        decode_error = error
        text = raw.decode("utf-8", errors="replace")
        line = raw[:error.start].replace(b"\r\n", b"\n").replace(b"\r", b"\n").count(b"\n") + 1
        result.add("INPUT-001", line, "input_error", "Checker requires UTF-8 input: {}".format(error.reason))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    check_format(text, result)
    lexical_rules = list((STRUCTURE_RULES if suffix == ".v" else ()) + SYNTAX_RULES
                         + (AST_RULES if suffix == ".v" else ()))
    if decode_error is not None:
        result.incomplete(lexical_rules, 1, "Invalid UTF-8 prevents reliable lexical checks.", "CHECK-001")
        return result.as_dict()
    tokens, comments, problem = lex(text)
    if problem is not None:
        result.incomplete(lexical_rules, problem[0], problem[1], "CHECK-001")
        return result.as_dict()
    if any(t.kind == "macro" or (t.kind == "directive" and t.value in {"define", "include"}) for t in tokens):
        result.notes.append("Source-only: includes and macros are not expanded or checked implicitly.")
    check_syntax(tokens, comments, result)
    if suffix == ".v":
        check_structure(tokens, result, path.stem)
        blocked = next((t for t in tokens if t.kind == "macro" or
                        (t.kind == "directive" and t.value not in
                         {"timescale", "default_nettype"})), None)
        if blocked:
            result.incomplete(AST_RULES, blocked.line,
                              "Structural checks require direct source; preprocessing "
                              "and include expansion are not covered.", "PARSE-001", reviewable=True)
        else:
            try:
                parsed = check_source(path=path, text=text, preprocessor_checked=True,
                                      existing_text=existing_text)
                result.diagnostics.extend(parsed["diagnostics"])
                result.unchecked.update(parsed["unchecked_rules"])
                result.notes.extend(parsed["notes"])
            except Exception as error:
                result.incomplete(AST_RULES, 1,
                                  "Structural checker failed: {}: {}".format(
                                      type(error).__name__, error), "CHECK-003")
    else:
        result.notes.append("Header fragment: module/process structure requires review in its include context.")
    return result.as_dict()


def build_report(filenames: Sequence[str], existing_sources=None) -> dict:
    existing_sources = existing_sources or {}
    files = [check_file(filename, existing_sources.get(str(Path(filename).expanduser().absolute())))
             for filename in filenames]
    if any(item["status"] == "incomplete" for item in files):
        exit_code, status = 2, "incomplete"
    elif any(item["status"] == "fail" for item in files):
        exit_code, status = 1, "fail"
    else:
        exit_code, status = 0, "pass"
    return {
        "schema_version": 1,
        "status": status,
        "exit_code": exit_code,
        "files": files,
        "summary": {
            "file_count": len(files),
            "violation_count": sum(d["kind"] == "violation" for f in files for d in f["diagnostics"]),
            "incomplete_count": sum(d["kind"] in {"incomplete", "input_error"}
                                    for f in files for d in f["diagnostics"]),
            "implemented_rules": list(ALL_RULES),
            "scope": "Direct-source lexical and parsed structural checks; full standards compliance also requires the source-bound AI review.",
            "not_covered": UNCOVERED,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format (default: text)")
    parser.add_argument("--baseline", metavar="FILE", help="Pre-edit source for existing port names (one input file)")
    parser.add_argument("files", nargs="+", metavar="FILE", help="Explicit .v/.vh file; no recursion or rewriting")
    args = parser.parse_args(argv)
    existing_sources = {}
    if args.baseline:
        if len(args.files) != 1:
            parser.error("--baseline requires exactly one input file")
        try:
            existing_sources[str(Path(args.files[0]).expanduser().absolute())] = (
                Path(args.baseline).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as error:
            parser.error("Cannot read baseline: " + str(error))
    report = build_report(args.files, existing_sources=existing_sources)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["files"]:
            for diagnostic in item["diagnostics"]:
                print("{path}:{line}: {rule_id} {kind}: {message}".format(**diagnostic))
            print("{}: {} (checked: {}; incomplete: {})".format(
                item["path"], item["status"].upper(), ", ".join(item["checked_rules"]) or "none",
                ", ".join(item["unchecked_rules"]) or "none"))
            for note in item["notes"]:
                print("  " + note)
        print("{}: {} file(s), {} violation(s), {} incomplete/input diagnostic(s).".format(
            report["status"].upper(), report["summary"]["file_count"],
            report["summary"]["violation_count"], report["summary"]["incomplete_count"]))
        print(report["summary"]["scope"])
        print("Not covered: " + "; ".join(report["summary"]["not_covered"]))
    return report["exit_code"]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

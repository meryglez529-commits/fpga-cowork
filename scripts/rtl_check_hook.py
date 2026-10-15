#!/usr/bin/env python3
"""Codex UserPromptSubmit/Stop adapter for RTL coding-standard checks.

Use repeated --include PROJECT_RELATIVE_DIRECTORY arguments. Runtime state and
reports live under the system temporary directory, never in the RTL tree. A
machine check cannot replace the required, source-bound AI standards review.
"""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
from check_rtl import build_report, lex


SKIP_DIRS = {
    ".git", ".codex", ".xil", "ip", "ips", "bd", "vendor", "third_party",
    "third-party", "ip_user_files", "ipstatic", "xsim.dir", "generated",
    "__pycache__", "node_modules",
}
SKIP_SUFFIXES = (".runs", ".cache", ".gen", ".sim", ".hw", ".ip_user_files")
STATE_VERSION = 1
REVIEW_VERSION = 2
BASELINE_FILE_BYTES = 512 * 1024
BASELINE_TOTAL_BYTES = 8 * 1024 * 1024
DIFF_LINES = 200
DIFF_CHARS = 12000
STANDARD_FILES = ("rtl-coding-standard.md",)
REFERENCES = Path(__file__).resolve().parent.parent / "references"


def _json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _relative(value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("include 必须是非空项目相对目录")
    parts = value.replace("\\", "/").split("/")
    if PureWindowsPath(value).drive or value.startswith(("/", "\\")) or ".." in parts:
        raise ValueError("include 不得使用绝对路径或 ..：" + value)
    if any(part in {"", "."} or ":" in part for part in parts):
        raise ValueError("include 目录格式无效：" + value)
    return Path(*parts)


def _context(payload, includes):
    if not isinstance(payload, dict):
        raise ValueError("hook 输入必须是 JSON 对象")
    for key in ("session_id", "turn_id", "cwd", "hook_event_name"):
        if not isinstance(payload.get(key), str) or not payload[key] or "\0" in payload[key]:
            raise ValueError("缺少有效的 " + key)
    event = payload["hook_event_name"]
    if event not in {"UserPromptSubmit", "Stop"}:
        raise ValueError("不支持的 hook 事件：" + event)
    if "stop_hook_active" in payload and not isinstance(payload["stop_hook_active"], bool):
        raise ValueError("stop_hook_active 必须为布尔值")
    cwd = Path(payload["cwd"])
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError("cwd 必须是存在的绝对目录")
    cwd = cwd.resolve(strict=True)
    root = next((p for p in (cwd, *cwd.parents)
                 if (p / ".git").exists() or (p / ".codex" / "hooks.json").is_file()), None)
    if root is None:
        raise ValueError("cwd 上级未找到 .git 或 .codex/hooks.json")
    if not includes:
        raise ValueError("至少指定一个 --include 手写源目录")
    scopes = []
    for value in includes:
        relative = _relative(value)
        directory = root / relative
        directory.resolve(strict=True).relative_to(root)
        if not directory.is_dir():
            raise ValueError("include 不是目录：" + str(relative))
        cursor = root
        for part in relative.parts:
            cursor /= part
            if _linked(cursor):
                raise ValueError("include 不得经过符号链接或 junction：" + str(relative))
            if part.lower() in SKIP_DIRS or part.lower().endswith(SKIP_SUFFIXES):
                raise ValueError("include 指向排除的生成目录：" + str(relative))
        scopes.append(relative.as_posix())
    return root, sorted(set(scopes))


def _snapshot(root, scopes, texts=None):
    hashes = {}
    text_bytes = 0

    def scan_error(error):
        raise error

    for scope in scopes:
        for folder, directories, filenames in os.walk(root / scope, followlinks=False,
                                                      onerror=scan_error):
            parent = Path(folder)
            directories[:] = sorted(name for name in directories
                                    if name.lower() not in SKIP_DIRS
                                    and not name.lower().endswith(SKIP_SUFFIXES)
                                    and not _linked(parent / name))
            for name in sorted(filenames):
                path = parent / name
                if path.suffix.lower() not in {".v", ".vh", ".sv", ".svh"} or _linked(path):
                    continue
                path.resolve(strict=True).relative_to(root)
                if not path.is_file():
                    continue
                name = path.relative_to(root).as_posix()
                raw = path.read_bytes()
                hashes[name] = hashlib.sha256(raw).hexdigest()
                if (texts is not None and len(raw) <= BASELINE_FILE_BYTES
                        and text_bytes + len(raw) <= BASELINE_TOTAL_BYTES):
                    try:
                        texts[name] = raw.decode("utf-8")
                        text_bytes += len(raw)
                    except UnicodeDecodeError:
                        pass  # The machine checker reports invalid UTF-8; review stays full-file.
    return hashes


def _state_read(path, root, scopes):
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("version") != STATE_VERSION
            or value.get("root") != str(root) or value.get("scopes") != scopes):
        raise ValueError("基线与当前项目/扫描范围不一致，请重新建立基线")
    if (not isinstance(value.get("turn_id"), str)
            or not isinstance(value.get("retry_requested"), bool)
            or not isinstance(value.get("stop_completed"), bool)):
        raise ValueError("基线状态无效")
    for field in ("baseline", "pending"):
        entries = value.get(field)
        if not isinstance(entries, dict):
            raise ValueError("基线内容无效")
        for name, digest in entries.items():
            _relative(name)
            if digest is None and field == "pending":
                continue
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)):
                raise ValueError("基线 hash 无效")
    return value


def _details(report, root):
    lines = []
    for result in report["files"]:
        for diagnostic in result["diagnostics"]:
            name = Path(diagnostic["path"]).relative_to(root).as_posix()
            message = diagnostic["message"].replace("\n", " ")[:140]
            lines.append(f"{name}:{diagnostic['line']} {diagnostic['rule_id']} {message}")
            if len(lines) == 8:
                return "\n".join(lines) + "\n其余项目见完整报告。"
    return "\n".join(lines)


def _standards(references):
    """Index numbered prose sections; this does not parse RTL semantics."""
    documents = {}
    for name in STANDARD_FILES:
        path = references / name
        raw = path.read_bytes()
        lines = raw.decode("utf-8-sig").splitlines()
        headings = []
        fenced = False
        for number, line in enumerate(lines, 1):
            if line.startswith(("~~~", "```")):
                fenced = not fenced
            if not fenced and re.match(r"^#{2,6} ", line):
                headings.append((number, line))
        sections = []
        for index, (number, heading) in enumerate(headings):
            match = re.match(r"^#{2,6} (\d+(?:\.\d+)*)\s+(.+)$", heading)
            end = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
            body = lines[number:end]
            if (match and not match[2].endswith("示例")
                    and any(line.strip() for line in body)):
                sections.append({"section": match[1], "title": match[2],
                                 "line": number, "end_line": end})
        if not sections:
            raise ValueError("规范正文没有可审查章节：" + str(path))
        documents[name] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                           "sections": sections}
    return documents


def _review_dependencies(root, names):
    """Bind literal include files without expanding macros or choosing branches."""
    dependencies, visited, issues = {}, {}, []

    def visit(path, dependency=False):
        name = path.relative_to(root).as_posix()
        try:
            if name in visited:
                if dependency:
                    dependencies[name] = visited[name]
                return
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            info = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                    "line_count": len(text.splitlines())}
            visited[name] = info
            if dependency:
                dependencies[name] = info
            tokens, unused_comments, problem = lex(text)
            if problem:
                issues.append(f"{name}:{problem[0]} 无法完整扫描 include 依赖：{problem[1]}")
                return
            for index, token in enumerate(tokens):
                if token.kind != "directive" or token.value != "include":
                    continue
                following = tokens[index + 1] if index + 1 < len(tokens) else None
                if not following or following.kind != "string" or following.line != token.line:
                    issues.append(f"{name}:{token.line} include 文件名不是可解析的同一行字面量。")
                    continue
                filename = following.value[1:-1].replace("\\", "/")
                try:
                    if (not filename or PureWindowsPath(filename).drive
                            or filename.startswith("/") or '"' in filename or "\0" in filename):
                        raise ValueError("include 必须是项目内相对于源文件的字面量路径")
                    target = Path(os.path.abspath(path.parent / filename))
                    relative = target.relative_to(root)
                    cursor = root
                    for part in relative.parts:
                        cursor /= part
                        if _linked(cursor):
                            raise ValueError("include 不得经过符号链接或 junction")
                    if not target.is_file():
                        raise ValueError("include 目标不是现存文件")
                    visit(target, True)
                except (OSError, ValueError) as error:
                    issues.append(f"{name}:{token.line} include {filename} 未解析：{error}")
        except (OSError, ValueError) as error:
            issues.append(f"{name} include 依赖未检查：{error}")

    for name in names:
        visit(root / name)
    return dict(sorted(dependencies.items())), issues


def _baseline_texts(hashes, *candidates):
    """Keep one bounded, hash-checked baseline; old hash-only states remain valid."""
    kept, total = {}, 0
    for name, digest in hashes.items():
        for candidate in candidates:
            text = candidate.get(name) if isinstance(candidate, dict) else None
            if not isinstance(text, str):
                continue
            try:
                raw = text.encode("utf-8")
            except UnicodeEncodeError:
                continue
            if (len(raw) <= BASELINE_FILE_BYTES and total + len(raw) <= BASELINE_TOTAL_BYTES
                    and hashlib.sha256(raw).hexdigest() == digest):
                kept[name] = text
                total += len(raw)
                break
    return kept


def _review_scopes(root, changed, state, report):
    """Diff is a navigation aid, never a claim that surrounding RTL is irrelevant."""
    baseline = state["baseline"]
    texts = _baseline_texts(baseline, state.get("baseline_text"))
    incomplete = {str(Path(item["path"]).resolve()) for item in report["files"]
                  if item["status"] == "incomplete"}
    scopes = {}
    for name in changed:
        path = root / name
        scope = {"mode": "full", "baseline_sha256": baseline.get(name)}
        if name not in baseline:
            scope["reason"] = "new_file"
        elif str(path.resolve()) in incomplete:
            scope["reason"] = "machine_coverage_gap"
        elif name not in texts:
            scope["reason"] = "baseline_text_unavailable"
        else:
            tokens, unused_comments, problem = lex(texts[name])
            if problem or any(token.kind == "macro" or
                              (token.kind == "directive" and token.value not in
                               {"timescale", "default_nettype"}) for token in tokens):
                scope["reason"] = "baseline_structure_unavailable"
                scopes[name] = scope
                continue
            raw = path.read_bytes()
            try:
                after = raw.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                after = None
            before = texts[name].splitlines()
            if after is None or len(raw) > BASELINE_FILE_BYTES:
                scope["reason"] = "source_text_unavailable_or_large"
            elif max(len(before), len(after)) > 10000:
                scope["reason"] = "large_file"
            else:
                edits = [item for item in difflib.SequenceMatcher(None, before, after).get_opcodes()
                         if item[0] != "equal"]
                amount = sum(max(b - a, d - c) for unused, a, b, c, d in edits)
                diff = list(difflib.unified_diff(before, after, fromfile="before/" + name,
                                               tofile="after/" + name, lineterm=""))
                diff_text = "\n".join(diff)
                if (amount > max(1, max(len(before), len(after)) // 2)
                        or len(diff) > DIFF_LINES or len(diff_text) > DIFF_CHARS):
                    scope["reason"] = "large_change"
                else:
                    # Starts are one-based positions; count=0 identifies an insertion/deletion.
                    # A deletion at EOF may have new_start == line_count + 1.
                    scope.update(mode="changed_with_context", reason="bounded_diff",
                                 changes=[{"old_start": a + 1, "old_count": b - a,
                                           "new_start": c + 1, "new_count": d - c}
                                          for unused, a, b, c, d in edits], diff=diff_text)
        scopes[name] = scope
    return scopes


def _review_request(root, changed, current, documents, dependencies, dependency_issues,
                    report_dir, payload, scopes, review_scopes, machine_report):
    hashes = {name: item["sha256"] for name, item in documents.items()}
    dependency_hashes = {name: item["sha256"] for name, item in dependencies.items()}
    source_hashes = {name: current[name] for name in changed}
    binding = {"schema_version": REVIEW_VERSION, "root": str(root), "sources": source_hashes,
               "standards": hashes, "dependencies": dependency_hashes,
               "dependency_issues": dependency_issues, "review_scopes": review_scopes}
    encoded = json.dumps(binding, sort_keys=True, ensure_ascii=False).encode("utf-8")
    review_id = hashlib.sha256(encoded).hexdigest()
    request_path = report_dir / "review-request.json"
    result_path = report_dir / "review-result.json"
    files = []
    sources = []
    for name in changed:
        path = root / name
        # Invalid text must still reach the machine checker and an unresolved review.
        count = len(path.read_bytes().decode("utf-8", errors="replace").splitlines())
        sources.append({"path": str(path), "relative_path": name,
                        "sha256": current[name], "line_count": count,
                        "review_scope": review_scopes[name]})
        files.append({"path": name, "source_sha256": current[name],
                      "reviewed": False, "findings": []})
    request = {
        "schema_version": REVIEW_VERSION, "review_id": review_id, "root": str(root),
        "documents": documents, "sources": sources, "result_path": str(result_path),
        "review_dependencies": dependencies, "dependency_issues": dependency_issues,
        "machine_check": {key: machine_report[key] for key in ("status", "summary", "files")
                          if key in machine_report},
        "refresh_hook_argv": [sys.executable, str(Path(__file__).resolve()),
                              *[argument for scope in scopes for argument in ("--include", scope)]],
        "refresh_hook_input": {"session_id": payload["session_id"], "turn_id": payload["turn_id"],
                               "cwd": str(root), "hook_event_name": "Stop", "stop_hook_active": True},
        "instructions": (
            "只检查编码规范符合性，不扩展为完整功能证明、设计评审或时序收敛。"
            "以本请求中的代码风格规范条文为准，不将协议、流水级、资源或 IP 选型作为风格违规。"
            "补查 machine_check 未可靠覆盖的适用规则；已可靠机器检查的内容"
            "不重复写通过证明。文内示例仅供参考写法，不把示例电路作为其他模块的设计要求；"
            "同一版本已读规则无需重复全文读取。"
            "按 sources[].review_scope 定位：full 审查完整文件；changed_with_context 从变更进入，"
            "扩读受影响的声明、完整逻辑块和信号使用处。diff 只是导航，不能只读 diff 就完成审查；"
            "状态、握手、时钟、复位关系需要沿相关路径扩读，范围无法确定时退回完整文件。"
            "只记录违规和无法判定项：findings 每项包含 document、section、status(fail/unresolved)、"
            "lines(至少一个当前源码有效行号)、reason；删除行的问题定位到当前相关逻辑。"
            "无需逐章 pass 证明或不适用规则的解释。完成该文件适用规则的补查后 reviewed=true；"
            "findings=[] 仅表示未发现问题，不能用于略过审查。填写 result_template 保存到 result_path。"
            "生产源目录内的 .sv/.svh 也必须审查，明确是否违反可综合 RTL 使用 Verilog-2001 的要求；"
            "不能因为检查器暂不支持该扩展名而忽略新增实现，测试代码应放在配置检查范围以外。"
            "预处理/结构覆盖缺口按完整相关结构审查，必须读取 review_dependencies 中递归收集的"
            "include 文件，审查源码及依赖的所有条件分支，"
            "不能只审当前配置激活的一支。头文件问题在包含它的源码行处记录 finding，并在 reason 中"
            "写明头文件位置。dependency_issues 未解决时检查不能完成。机器标记 reviewable 的"
            "覆盖缺口可由此次明确审查补充，最终仅能记为 reviewed_with_limits，不能改称机器全通过。"
            "源码、规范、依赖或 review_scope 改变后 review_id 失效，不得手改 hash 冒充已审新版本。"
            "修复源码后，按 refresh_hook_argv 执行，将 refresh_hook_input 的 JSON 写到其 stdin，"
            "再读取刷新后的本请求，审查最终源码并填写结果。"
        ),
        "result_template": {"schema_version": REVIEW_VERSION, "review_id": review_id,
                            "standards_sha256": hashes, "dependencies_sha256": dependency_hashes,
                            "files": files},
    }
    _json_write(request_path, request)
    return request, request_path, result_path


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _review_result(request, result_path):
    """Validate review coverage and version binding, not truth of AI judgments."""
    if not result_path.is_file():
        return {"status": "missing", "issues": ["尚无 AI 编码规范审查结果。"]}
    try:
        if result_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("审查结果超过 4 MiB")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        template = request["result_template"]
        if not isinstance(result, dict) or result.get("schema_version") != REVIEW_VERSION:
            raise ValueError("审查结果 schema_version 必须为 2")
        if (result.get("review_id") != request["review_id"]
                or result.get("standards_sha256") != template["standards_sha256"]
                or result.get("dependencies_sha256") != template["dependencies_sha256"]):
            return {"status": "stale", "issues": ["源码、include 依赖、规范版本或审查范围已变，原结果过期。"]}
        files = result.get("files")
        expected_files = {item["path"]: item for item in template["files"]}
        if not isinstance(files, list) or len(files) != len(expected_files):
            raise ValueError("审查结果未完整覆盖本次所有变更文件")
        seen = set()
        issues = []
        for file_result in files:
            if not isinstance(file_result, dict):
                raise ValueError("审查 files 项必须是对象")
            name = file_result.get("path")
            if not isinstance(name, str) or name not in expected_files or name in seen:
                raise ValueError("审查文件缺失、重复或不在本次范围内")
            seen.add(name)
            expected = expected_files[name]
            if file_result.get("source_sha256") != expected["source_sha256"]:
                return {"status": "stale", "issues": [name + " 源码 hash 与审查不符。"]}
            line_count = next(item["line_count"] for item in request["sources"]
                              if item["relative_path"] == name)
            if file_result.get("reviewed") is not True:
                raise ValueError(name + " 尚未确认完成所需范围的规范补查（reviewed=true）")
            findings = file_result.get("findings")
            if not isinstance(findings, list):
                raise ValueError(name + " findings 必须为数组")
            for finding in findings:
                if not isinstance(finding, dict):
                    raise ValueError("findings 项必须是对象")
                document = finding.get("document")
                section = finding.get("section")
                status = finding.get("status")
                lines = finding.get("lines")
                if not isinstance(document, str) or document not in request["documents"]:
                    raise ValueError(name + " 发现项缺少有效规范文档")
                sections = {item["section"] for item in request["documents"][document]["sections"]}
                if not isinstance(section, str) or section not in sections:
                    raise ValueError(name + " 发现项缺少有效规范章节")
                if status not in {"fail", "unresolved"} or not _nonempty(finding.get("reason")):
                    raise ValueError(name + " §" + section + " 缺少问题结论或具体理由")
                if (not isinstance(lines, list) or not lines or any(type(line) is not int
                        or line < 1 or line > line_count for line in lines)):
                    raise ValueError(name + " §" + section + " 缺少有效源码行号")
                issues.append(f"{name}:{','.join(map(str, lines))} {document} §{section} "
                              f"{status}: {finding['reason']}")
        return {"status": "fail" if issues else "pass", "issues": issues,
                "evidence": result}
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"status": "incomplete", "issues": ["AI 规范补查记录不完整：" + str(error)]}


def _reviewable_machine_limits(report):
    diagnostics = [item for file_result in report["files"] for item in file_result["diagnostics"]]
    return (report["status"] == "incomplete" and bool(diagnostics)
            and all(item["kind"] == "incomplete" and item.get("reviewable") is True
                    for item in diagnostics)
            and all(file_result["status"] != "incomplete" or file_result["diagnostics"]
                    for file_result in report["files"]))


def handle(payload, includes, state_home=None, references=None):
    """Return one hook JSON object; state_home is injectable for isolated tests."""
    home = Path(state_home) if state_home else Path(tempfile.gettempdir()) / "fpga-cowork-rtl-hooks"
    references = Path(references) if references else REFERENCES
    report_dir = home / "errors"
    try:
        root, scopes = _context(payload, includes)
        identity = json.dumps([payload["session_id"], str(root)], ensure_ascii=False)
        report_dir = home / hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        state_path = report_dir / "state.json"
        state = _state_read(state_path, root, scopes)
        event = payload["hook_event_name"]
        if event == "UserPromptSubmit" and state and state["turn_id"] == payload["turn_id"]:
            return {}
        if event == "Stop" and state and state["stop_completed"]:
            state["stop_completed"] = False
            _json_write(state_path, state)
        captured_text = {} if event == "UserPromptSubmit" else None
        current = _snapshot(root, scopes, captured_text)
        if event == "UserPromptSubmit":
            pending = state["pending"] if state else {}
            if state and not state["stop_completed"]:
                current = dict(state["baseline"])
                captured_text = state.get("baseline_text", {})
            for name, digest in pending.items():
                if digest is None:
                    current.pop(name, None)
                else:
                    current[name] = digest
            _json_write(state_path, {
                "version": STATE_VERSION, "root": str(root), "scopes": scopes,
                "turn_id": payload["turn_id"], "baseline": current, "pending": pending,
                "baseline_text": _baseline_texts(current, captured_text,
                                                 state.get("baseline_text") if state else None),
                # A new user turn may request one retry again. Codex marks automatic
                # Stop continuations with stop_hook_active, including a new turn ID.
                "retry_requested": False,
                "stop_completed": False,
            })
            return {}
        if state is None:
            raise ValueError("没有本轮编码前基线，无法确认变更文件；请手动检查本轮文件")
        if state["turn_id"] != payload["turn_id"] and not state["pending"]:
            raise ValueError("当前 turn_id 没有对应基线；请手动检查本轮文件")
        changed = sorted(name for name, digest in current.items()
                         if state["baseline"].get(name) != digest)
        if not changed:
            state["pending"] = {}
            state["stop_completed"] = True
            _json_write(state_path, state)
            return {}
        documents = _standards(references)
        dependencies, dependency_issues = _review_dependencies(root, changed)
        checked_names = sorted(set(changed) | set(dependencies))
        baseline_texts = _baseline_texts(state["baseline"], state.get("baseline_text"))
        report = build_report([str(root / name) for name in checked_names],
                              existing_sources={str(root / name): text
                                                for name, text in baseline_texts.items()})
        review_scopes = _review_scopes(root, changed, state, report)
        request, request_path, result_path = _review_request(
            root, changed, current, documents, dependencies, dependency_issues,
            report_dir, payload, scopes, review_scopes, report)
        review = _review_result(request, result_path)
        if (_snapshot(root, scopes) != current or _standards(references) != documents
                or _review_dependencies(root, changed) != (dependencies, dependency_issues)):
            raise ValueError("检查期间 RTL 文件、include 依赖或编码规范再次改变，请重新检查")
        machine_status = report["status"]
        reviewable_limits = _reviewable_machine_limits(report)
        report["machine_status"] = machine_status
        report["ai_review"] = review
        report["review_dependencies"] = dependencies
        report["dependency_issues"] = dependency_issues
        report["status"] = "incomplete"
        if review["status"] == "pass" and not dependency_issues:
            if machine_status == "pass":
                report["status"] = "pass"
            elif reviewable_limits:
                report["status"] = "reviewed_with_limits"
        if machine_status == "fail" or review["status"] == "fail":
            report["status"] = "fail"
        report["exit_code"] = {"pass": 0, "reviewed_with_limits": 2,
                               "fail": 1, "incomplete": 2}[report["status"]]
        report["hook"] = {"session_id": payload["session_id"], "turn_id": payload["turn_id"],
                          "root": str(root), "includes": scopes, "changed_files": changed,
                          "review_scopes": review_scopes,
                          "review_request": str(request_path), "review_result": str(result_path)}
        report_path = report_dir / ("report-" + uuid.uuid4().hex + ".json")
        _json_write(report_path, report)
        state["stop_completed"] = True
        if report["status"] in {"pass", "reviewed_with_limits"}:
            state["pending"] = {}
            _json_write(state_path, state)
            if report["status"] == "reviewed_with_limits":
                return {"systemMessage": f"RTL 编码规范检查完成（reviewed_with_limits）："
                        f"{len(changed)} 个变更文件无已知机器违规；机器检查仍为 incomplete，"
                        "已标记 reviewable 的覆盖缺口由 AI 规范审查补充，含递归 include 依赖及全部条件分支。"
                        "这不是机器全部通过，也不代表功能或时序通过。"
                        f"限制及检查记录：{report_path}"}
            return {"systemMessage": f"本轮 RTL 编码规范检查完成：{len(changed)} 个变更文件的全文件机器检查通过；"
                    "AI 已按请求范围补查新模块或改动及相关上下文，无已报告的违规和未决项。"
                    f"这不等于既有源码全部规则、功能或时序通过。完整报告：{report_path}"}
        repeated = state["retry_requested"] or payload.get("stop_hook_active", False)
        # Keep every changed file until the complete check passes. A later turn
        # must not silently turn unresolved or unreviewed source into its baseline.
        state["pending"] = {name: state["baseline"].get(name) for name in changed}
        state["retry_requested"] = True
        _json_write(state_path, state)
        review_issues = "\n".join(review["issues"][:8])
        summary = (f"RTL 编码规范检查未通过（机器检查 {machine_status}；AI 审查 {review['status']}）。\n"
                   f"{_details(report, root)}\n{review_issues}\n"
                   + "\n".join(dependency_issues[:8]) + f"\n完整报告：{report_path}")
        if repeated:
            return {"systemMessage": summary + "\n自动复检仍未通过，不再自动续做；不得将其报告为检查通过。"}
        return {"decision": "block", "reason": summary + "\n请完成自动触发的编码规范补查：读取 "
                f"{request_path}，按 review_scope 审查机器未覆盖的适用规则。机器仍检查变更整文件；"
                "AI 对 full 范围读完整文件，对 changed_with_context 从 diff 扩读受影响逻辑，不能只读 diff。"
                "规范同版本已读可复用，专题与示例按需读取。修复违规后填写 result_template："
                f"逐文件 reviewed=true，只在 findings 记录违规/未决项，保存为 {result_path}。"
                "不写逐章通过证明或不适用理由；未实际补查不能确认 reviewed；"
                "机器明确违规或未标记 reviewable 的失败不能用 AI pass 覆盖；"
                "仅可审查补充的覆盖缺口完成后保留 reviewed_with_limits 结论。请先修复再读取最新请求；"
                "若修复使请求 hash 过期，按请求中的 refresh_hook_argv / refresh_hook_input 重跑，"
                "以刷新请求后审查最终源码。完成后正常结束，由 hook 自动核验与复检。"
                "不得为过检查改变电路行为、削弱规则、仅更新 hash 或将未审项目写为 pass。"}
    except (OSError, ValueError, TypeError, KeyError) as error:
        message = "RTL hook 未检查：" + str(error)
        try:
            path = report_dir / ("not-checked-" + uuid.uuid4().hex + ".json")
            _json_write(path, {"status": "not_checked", "message": message})
            message += "。报告：" + str(path)
        except OSError:
            message += "；同时无法保存报告。"
        return {"systemMessage": message}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, exit_on_error=False)
    parser.add_argument("--include", action="append", default=[])
    try:
        args, extra = parser.parse_known_args(argv)
        if extra:
            raise ValueError("未知参数：" + " ".join(extra))
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("hook 输入超过 1 MiB")
        result = handle(json.loads(raw.decode("utf-8")), args.include)
    except (ValueError, argparse.ArgumentError) as error:
        result = {"systemMessage": "RTL hook 未检查：" + str(error)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

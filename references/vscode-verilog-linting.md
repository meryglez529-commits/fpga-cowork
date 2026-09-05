# VS Code HDL Lint 配置

Mode 1 必须建立项目根 `.vscode/settings.json`。目标是让编辑器诊断复现工程的真实编译上下文，或在上下文尚未可验证时不显示单文件误报；它不替代 Vivado 仿真、综合或实现。

## 1. 先判断能否启用 linter

从 `.xpr`/`.qpf`、项目 Tcl、compile script、filelist 或已验证的仿真命令确认：

- 使用的 HDL linter 和可执行路径；
- 源文件顺序、include 目录、全局宏头文件和 `-d` 宏；
- IP、BD、加密模型或库边界；
- 至少一个顶层或代表性活动 RTL 文件的完整单文件诊断命令。

许多 VS Code HDL 扩展只对当前文档调用 `xvlog`。这不会自动读取 Vivado `.xpr` 的编译顺序，也不会加载没有被 `` `include`` 的全局 `*.vh` 宏文件；`includePath` 只帮助已写出的 `` `include``。不要把这种宏/源顺序缺失显示为 RTL 故障。

## 2. 默认安全配置

若项目上下文尚未验证，创建或合并以下项目级设置：

```json
{
  "verilog.linting.linter": "none"
}
```

这只禁用该工作区的自动单文件 HDL lint，不影响 Vivado 工程、构建或其它 VS Code 功能。将未配置原因记录到 `AI-work/env/ENVIRONMENT.md` 或 `AI-work/OPEN-QUESTIONS.md`。

## 3. 已验证的 xvlog 配置

仅当下面命令对代表性源返回预期结果后，才启用 `xvlog`。路径数组使用相对项目根的目录；宏头/filelist 参数必须是该项目的真实输入，不能从另一个工程复用。

```json
{
  "verilog.linting.linter": "xvlog",
  "verilog.linting.path": "D:\\Xilinx\\Vivado\\<version>\\bin",
  "verilog.linting.xvlog.includePath": [
    "rtl",
    "rtl/include"
  ],
  "verilog.linting.xvlog.arguments": "<verified-global-header-or-filelist-arguments>"
}
```

For `mshr-h.veriloghdl`, custom xvlog arguments appear before the active document. A global macro header may therefore be supplied as a verified source argument; a verified `-f`/`--file` list is preferable when it faithfully models the project without compiling the active document twice. Test the exact extension-shaped command in an `AI-work/reports/baseline/<id>/tool/` subdirectory:

```text
xvlog -nolog -i <include-dir> ... <verified-prelude> <active-source.v>
```

Keep output and manual logs under `AI-work/`; do not use a project-root or drive-root work directory. If this command still reports undefined macros, missing includes, duplicate design units, or IP/library errors caused by incomplete context, return to `linter: none` and record the gap.

## 4. Existing settings and global behavior

- Merge only `verilog.linting.*` keys into an existing workspace settings file. Preserve all unrelated editor, formatter, task and extension settings.
- Never add project-specific absolute headers or include paths to the user-level VS Code settings.
- A user may explicitly request a global default that avoids false positives across unknown HDL projects. In that case set only `"verilog.linting.linter": "none"` at user scope; project workspaces then opt in with verified settings.
- Reload the VS Code window after editing settings so stale diagnostics are cleared.

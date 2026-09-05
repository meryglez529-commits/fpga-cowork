# <UNIT> 实施进度跟踪

> 本文件记录实施状态、改动、命令、日志、错误修复和证据路径。它必须和代码/日志保持同步。

配套文档：

- 需求：[REQUIREMENTS.md](REQUIREMENTS.md)
- 架构：[ARCHITECTURE.md](ARCHITECTURE.md)
- 仿真复现：[sim/SIM_REPLAY.md](sim/SIM_REPLAY.md)

## 1. 当前结论

| 项 | 状态 | 证据 |
|---|---|---|
| RTL 修改 | 未开始 | |
| RTL elaboration | 未运行 | |
| S — 项目仿真 | 未选择 | |
| B — 构建与 bitstream | 未选择 | |
| H — 硬件与 ILA/VIO | 未选择 | |
| D — 只读诊断 | 未选择 | |

## 2. 实施顺序

- [ ] 1. 需求确认
- [ ] 2. 架构方案与 S/B/H/D 选择确认
- [ ] 3. RTL 修改
- [ ] 4. RTL elaboration
- [ ] 5. 已选择的 S/B/H/D 流程
- [ ] 6. As-built 回写

## 3. RTL 改动状态

| 文件 | 状态 | 改动说明 | 风险 |
|---|---|---|---|
| `<path>` | todo | | |

## 4. 已选择流程记录

| 时间 | 流程/场景 | 结果 | 证据 |
|---|---|---|---|
| | | | |

## 5. 工具运行与归档记录

| 项 | 路径/命令 | 状态 |
|---|---|---|
| unit root | `AI-work/features/<feature-slug>/<UNIT>` | |
| artifact marker | `AI-work/features/<feature-slug>/<UNIT>/out/.artifact_start` | |
| Vivado log/journal 策略 | `<所有 -log/-journal 指向当前 unit out/*>` | |
| 流程包目录 | `sim` / `build` / `hardware` / `diagnostics`（仅已选择流程） | |
| 流程输出目录 | `out/sim` / `out/build` / `out/ila` / `out/diagnostics`（仅已选择流程） | |
| spill scan | `python <skill>/scripts/scan-artifact-spill.py <project-root> --since-file <UNIT>/out/.artifact_start --allowed-root <UNIT>` | |

## 6. 问题跟踪

### 已解决

| 问题 | 修复 | 证据 |
|---|---|---|
| | | |

### 待解决

| 问题 | 影响 | 下一步 |
|---|---|---|
| | | |

## 7. 变更记录

| 日期 | 文件/阶段 | 变更内容 | 负责人 |
|---|---|---|---|
| | | | |

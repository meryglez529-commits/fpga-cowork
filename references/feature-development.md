# Mode 3 — 需求工作包闭环

```text
需求 → AI 方案 → 用户确认 → 实现 → 验证 → 结果与验收 → 用户确认 → 提交/推送
```

## 计划

创建：

```text
AI-work/work-packages/<需求名>-<日期>/
  PLAN.md
  EXECUTION.md
  ACCEPTANCE.md
```

`PLAN.md` 只说明当前需求：目标与边界、相关硬件事实及来源、用户指定的 `.xpr`、拟修改
的工程输入、选用的 S/B/H/D、板级操作、验收标准。仿真、构建或硬件操作应标明将使用的
fileset、run 或硬件目标，以及其原生产物位置。

缺少硬件事实时，先追溯并更新 `HARDWARE_ENVIRONMENT.md`；未指定 `.xpr` 时停在计划
阶段。用户确认计划后，才可实施其中的工程修改、构建或板级操作。

## 执行

只在计划指定的 `.xpr` 上操作。RTL、XDC、testbench、IP、ILA、VIO 和必要 Tcl 均放在
该工程正常 GUI 目录并注册在工程中；Vivado 原生产物留在该工程的 `.sim/`、`.runs/` 或
`.hw/`。AI-work 仅记录命令、结果、解释及原生产物路径。

RTL、XDC、IP、ILA、VIO、Block Design 或工程设置改动后，按交付目标重新构建；下载
使用该工程构建的 `.bit`，ILA 或 VIO 使用同一次实现生成的匹配 `.bit` / `.ltx`。

`EXECUTION.md` 记录实际改动、实际执行结果、偏差和停止原因。若需求或硬件事实与计划
不符，停止相关操作，更新计划并重新确认。

## 验收与提交

`ACCEPTANCE.md` 对照计划记录交付内容、修改文件、S/B/H/D 证据、适用的时序/DRC/仿真
或板级结论、未验证项和限制，并给出 `PASS`、`FAIL`、`BLOCKED` 或 `PARTIAL` 状态。

构建成功不等于功能或板级成功；仿真和 ILA 结论仅覆盖已执行的场景、信号和时段。等待
用户验收确认后再提交或推送，除非已获明确预授权。

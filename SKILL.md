---
name: fpga-cowork
description: 在既有 Vivado GUI 工程中建立可追溯硬件环境，并以计划、执行、验收闭环协作完成 FPGA 功能开发。
metadata:
  version: 2.1.1
---

# FPGA 协作开发

本技能把人机协作流程与 Vivado 操作区分开：Mode 定义协作关系；S、B、H、D
是按当前需求选用的 Vivado 操作流程。

## 模式选择

| 模式 | 适用情况 | 记录位置 |
|---|---|---|
| **Mode 1 — 工程阅读** | 阅读、接手或梳理既有工程。 | `AI-work/mode1/`，仅在需要留存时记录。 |
| **Mode 2 — 单文件阅读或注释** | 解释、比较或仅添加注释。 | `AI-work/mode2/`，仅在需要留存时记录。 |
| **Mode 3 — 需求工作包闭环** | 新功能、设计修改或该功能的验证。 | `AI-work/work-packages/<需求名>-<日期>/`。 |
| **Mode 4 — 板卡环境初始化** | 该板卡尚无可复用的 AI 硬件环境。 | `AI-work/` 的全局基础文件。 |

Mode 4 对一块协作环境尚未建立的板卡只执行一次；之后的新功能均使用 Mode 3。
Mode 1、Mode 2 不构成 Mode 3 的前置条件。D 可用于独立的只读问题。用户明确要求的
独立 S、B、H 操作也必须在 `AI-work/<flow>/<标识>/` 创建 `PLAN.md`、`EXECUTION.md`
和 `ACCEPTANCE.md`；如果操作需要修改设计输入或工程设置，则进入 Mode 3，不适用该例外。

## Mode 4 — 板卡与协作环境初始化

Mode 4 初始化下列供后续所有模式共用的文件和目录：

```text
AI-work/
  README.md
  LOG.md
  HARDWARE_ENVIRONMENT.md
```

Mode 1、Mode 2 和工作包目录在实际首次需要记录时创建。

`HARDWARE_ENVIRONMENT.md` 是共享硬件事实来源。它记录 FPGA/封装、Bank 供电、
JTAG 与配置事实、资料来源、每张已审阅 FPGA 页的逐信号映射、已追踪功能路径和
待确认项。每条映射标明视觉确认、文本提取或用户确认等证据状态。用于管脚、
IOSTANDARD、时钟、时序、IP 参数或板级动作的事实必须能追溯到原理图、数据手册
或用户确认；未知项不得猜测使用。

环境可以是 `PARTIAL`：未使用接口不阻塞已经具备全部所需事实的功能工作包；当前
需求涉及的接口则必须具备所需的管脚、电压、极性、时钟和端到端连线证据。

Mode 4 不创建 Vivado 工程、`.xpr`、RTL、XDC、IP、Tcl、bitstream 或板级动作。
用户通过 GUI 创建或指定正常 Vivado 工程；后续 Mode 3 计划引用该既有 `.xpr`。

需要时阅读 [新板卡环境](references/new-board-development.md)。

## Mode 3 — 需求工作包闭环

每项功能需求遵循：

```text
需求 → AI 方案 → 用户确认 → 实现 → 验证 → 结果与验收 → 用户确认 → 提交/推送
```

实现前，在工作包中创建 `PLAN.md`、`EXECUTION.md` 和 `ACCEPTANCE.md`。计划仅说明
当前需求的目标与边界、相关硬件事实和来源、既有 `.xpr`、拟修改的工程输入、选用的
S/B/H/D 流程、板级操作及验收标准。缺少硬件事实时，先追溯并更新
`HARDWARE_ENVIRONMENT.md`；未指定 `.xpr` 时停在计划阶段，请用户创建或选择工程。

用户确认计划后，才可修改 RTL、XDC、IP、Block Design、ILA、VIO 或工程设置，或
执行下载、ILA、VIO、Flash 等板级状态改变操作。执行记录实际改动、命令、原生产物
路径、偏差和停止原因；验收记录证据、结论、限制和未验证项。用户接受验收后才提交
或推送，除非已明确预授权。

需要时阅读 [需求工作包](references/feature-development.md)。

## Mode 1 和 Mode 2

Mode 1 是轻量工程阅读；只将需要在对话后保留的结论写入 `AI-work/mode1/`。

Mode 2 的解释或比较是只读操作。用户明确要求添加注释时，只修改指定范围的注释，
不改变端口、逻辑、约束、IP 或工程设置；记录范围和“仅注释变更”的检查结果。若
发现需要功能改变，转入 Mode 3。

需要时阅读 [单文件阅读或注释](references/single-file-close-reading.md)。

## 单一 Vivado 工程上下文

AI 的所有 Vivado 操作必须使用用户已创建或指定的一份既有 `.xpr`。该工程的已注册
fileset、IP、Block Design、run、仿真和 Hardware Manager 构成唯一上下文；不得创建、
克隆或使用平行 Vivado 工程。

RTL、XDC、testbench、IP、ILA、VIO、Block Design 及必要工程 Tcl 均属于该工程并
放在其 GUI 工程结构中。所有 Vivado 原生产物均留在同一工程上下文：仿真数据位于
`<工程>.sim/`，综合、实现、`.bit`、`.ltx` 和原生报告位于 `<工程>.runs/`，
Hardware Manager 状态和 `.ila` 位于 `<工程>.hw/`，其他 GUI 生成目录（如
`.cache/`、`.gen/`、`.ip_user_files/`、`.Xil/`）以及 Vivado 原生日志和 journal
同样留在工程内。`AI-work` 只保存协作记录、分析结论、少量关键文本摘录和原生产物的
绝对路径；不复制原生 WDB、WCFG、bitstream、LTX、ILA、日志或 journal 数据。

## 操作流程

| 流程 | 适用情况 | 工程原生产物 | AI 记录 |
|---|---|---|---|
| **S — 仿真** | 需要 DUT/场景的仿真证据。 | 已选 simulation fileset 和 `<工程>.sim/`。 | 工作包 `out/sim/<标识>/`，或独立请求的 `AI-work/sim/<标识>/`。 |
| **B — 构建** | 需要综合、实现、时序或 bitstream。 | 既有工程的 `.runs/`。 | 工作包 `out/build/<标识>/`，或独立请求的 `AI-work/build/<标识>/`。 |
| **H — 硬件 / ILA / VIO** | 需要下载、板级观察、ILA 或 VIO。 | `<工程>.hw/` 及其原生备份。 | 工作包 `out/ila/`、`out/hardware/`，或独立请求对应位置。 |
| **D — 只读诊断** | 解释既有源文件、报告、日志或采集数据。 | 无。 | 工作包 `out/diagnostics/`，或 `AI-work/diagnostics/`。 |

只选择当前需求需要的流程，不因流程名称自动补跑其他阶段。需要时分别阅读：

- [S — 仿真](references/simulation-environment.md)
- [B — 构建](references/build-environment.md)
- [H — 硬件、ILA、VIO](references/hardware-debug-environment.md)
- [D — 只读诊断](references/read-only-diagnostics.md)

## 基本边界

- 用户维护的 RTL、XDC、IP 配置、Block Design 和工程设置，只能按获批计划修改。
  获批的重新综合、实现、仿真或硬件采集正常更新 `.runs/`、`.sim/`、`.hw/` 内的
  原生产物，不视为覆盖用户维护内容。
- RTL、XDC、IP、ILA、VIO、Block Design 或工程设置改动后，必须进行与交付目标相符
  的重新构建；下载使用该工程构建的 `.bit`，ILA 或 VIO 则使用同一次实现生成的匹配
  `.bit` / `.ltx`。
- 启动 S、B、H 前，只检查 AI 本次实际需要写入或使用的具体仿真输出、run 或硬件
  工作区是否已被占用。仅打开 Vivado GUI 不构成冲突；若目标资源确实被占用，停止
  该操作并如实汇报，不抢占进程、不移动输出、不复制工程绕过。
- 下载、ILA 捕获、VIO 写入、Flash 写入及其他板级状态改变操作，必须在计划中明确
  并经用户确认。JTAG 下载默认是易失配置，除非明确要求非易失操作。
- 不将未执行、失败、证据不足或仅部分完成的检查写成通过；仿真、构建和 ILA 结论
  均只覆盖其实际验证范围。
- 不为了流程而增加无关目录、脚本、模板、校验器或报告层。

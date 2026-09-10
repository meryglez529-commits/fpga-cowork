---
name: fpga-cowork
description: 在用户指定的既有 Vivado GUI 工程中，按项目与模块架构协作完成 FPGA 设计、仿真、构建、硬件调试和只读诊断。
metadata:
  version: 3.2.0
---

# FPGA 协作开发

本技能管理两部分：用工程文档维持 AI 与人的设计上下文；用同一份 Vivado GUI 工程管理
设计输入和原生产物，并在此基础上执行 S、B、H、D 流程。

## 工程文档

工程文档记录当前有效的工程结构和技术设计，用于维持用户与 AI 共同开发所需的上下文。
技能自身的协作规则不写入工程文档，工程文档也不作为开发过程日志。

工程文档按需要独立维护设计上下文的设计单元组织，而不是按当前 RTL 例化层次组织。一个
设计单元无论当前作为 Vivado top 独立验证，还是被其他模块例化，其文档归属都保持不变。
例化已有模块不会导致其文档被移动或复制。

```text
AI-work/
  ARCHITECTURE.md
  modules/
    <design-unit>/
      MODULE.md
```

只为需要独立维护设计上下文的设计单元建立模块文档。开始任务时先读取
`ARCHITECTURE.md`，再读取当前工作涉及的 `MODULE.md`。

### ARCHITECTURE.md

`ARCHITECTURE.md` 描述工程整体的当前结构，包括工程身份、工程中的设计单元、相应的代码
和文档入口，以及已经形成的例化、依赖和集成关系。彼此独立或处于相同层级的设计单元可以
作为多个根节点登记。Vivado 当前使用的 top 属于工程状态，也在这里维护。

它只描述工程整体及设计单元之间的关系，不展开设计单元内部实现。

### MODULE.md

`MODULE.md` 描述所属设计单元当前有效的技术设计。对于新设计单元或实质性设计调整，在开始
RTL 开发前，先将设计思路整理到足以让用户审阅并指导实现的程度。用户不必先阅读 RTL，
就应当能够理解该设计准备怎样实现、为什么这样设计，并据此发现问题或提出修改意见。

文档如何组织由设计本身决定。设计发生变化时，直接修订受影响的内容并清除已经被否定的
方案，使文档重新收敛为一套完整、前后一致的当前设计，而不是在旧方案上累积补充说明。
实现和验证完成后，继续使文档与实际设计保持一致。

一个设计单元使用另一个已有设计单元时，在 `ARCHITECTURE.md` 中维护双方的关系。使用方
可以在自己的 `MODULE.md` 中说明与本方设计有关的集成方式并引用对方文档，但不重复对方
的内部设计。

除上述文档外，只在用户要求时创建其他工程文档。

## Vivado 工程上下文

用户通过 GUI 创建或指定的 `.xpr` 是 AI 与人共享的 Vivado 工程上下文。用户尚未指定时，
请用户创建或选择工程。

### 输入

FPGA 开发输入包括 RTL、testbench、XDC、IP、Block Design、ILA 和 VIO。新增或修改的输入
沿用工程现有布局，登记到正确的 design、simulation 或 constraint fileset 并保存工程。
Tcl 自动化打开这份 `.xpr` 并操作其中已登记的对象，使批处理与 GUI 使用相同的源、top、
compile order、IP、约束和 run。

继续开发时优先使用工程中已有的 XDC。当前接口缺少约束时，查阅相关原理图；原理图仍无法
确定时向用户询问。确定后更新工程 XDC，并在相关 `MODULE.md` 中维护该接口的设计信息。

### 原生产物

Vivado 原生产物留在该工程的原生位置，使用户可以直接通过 GUI 查看和继续操作：

- 仿真结果、WDB 和 WCFG 位于 `<工程>.sim/`；
- 综合、实现、报告、bitstream 和 LTX 位于 `<工程>.runs/`；
- Hardware Manager 状态、ILA 数据和采样导出位于 `<工程>.hw/`；
- IP、缓存和生成内容沿用工程的 `.srcs/`、`.gen/`、`.cache/`、`.ip_user_files/`、`.Xil/`
  等原生目录；Vivado 原生 log 和 journal 留在工程原生运行目录。

AI 启动 `vivado -mode batch` 时，将每次调用的 log 和 journal 成对放入 `<工程>/logs/`，
文件名包含流程名称和唯一调用标识；不得重复使用已有的 `-log` 或 `-journal` 路径，避免
Vivado 生成无法明确对应本次执行的 `*.backup.*` 文件。判断一次流程的执行结果时，只读取
本次调用对应的 log、journal 和当前轮次的原生 run 结果，不把旧日志或 backup 日志计入
本次结论。

`AI-work` 只保存工程架构、模块设计和用户要求的开发记录，不复制上述原生产物。流程完成后，
在对话中给出所用 `.xpr`、工程对象、结果和原生产物的绝对路径，便于用户在 GUI 中检查。

### S、B、H、D

AI 或用户根据当前目标按需选择流程。只要 AI 使用 Vivado 进行下列操作，必须先完整读取并
遵循对应规范；Tcl 只是规范内部的执行手段。各流程独立，同一任务可分别使用多套流程，
流程之间不互相调用。

| 流程 | Vivado 操作 | 规范 |
|---|---|---|
| **S — 仿真** | 启动、修改或重新运行 Vivado 仿真 | [S — 仿真](references/simulation-environment.md) |
| **B — 构建** | 综合、实现、时序、DRC 或生成 bitstream | [B — 构建](references/build-environment.md) |
| **H — 硬件** | JTAG、下载、Hardware Manager、ILA、VIO 或 Flash | [H — 硬件](references/hardware-debug-environment.md) |
| **D — 诊断** | 只读分析代码、工程状态、报告、日志或已有采集 | [D — 诊断](references/read-only-diagnostics.md) |

设计输入改变只表示已有构建结果或镜像可能不再对应当前工程，不单独触发 B 或 H。需要实际
上板时，检查板上已下载的 bitstream 以及 Hardware Manager 使用的 LTX 是否对应当前工程输入：不一致时分别执行 B
更新镜像和 H 下载或调试；仍然一致时直接执行 H。

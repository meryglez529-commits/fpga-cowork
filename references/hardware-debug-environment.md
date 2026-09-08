# H — 硬件、ILA、VIO

H 用于下载、受限板级观察、ILA 捕获或 VIO 操作。它通过用户指定 `.xpr` 的 Hardware
Manager 上下文运行，不建立脱离工程的硬件会话或工程副本。

## 计划

写明目标板卡、JTAG target、FPGA 器件、使用的 `.bit`，以及 ILA/VIO 时匹配的 `.ltx`、
ILA 核或 VIO 对象、触发/写入条件、超时、预期观察和验收标准。下载、ILA 捕获、VIO 写入、Flash 写入及
其他板级状态改变操作必须在计划中明确并经用户确认。

ILA/VIO IP、RTL 例化、约束、debug bitstream 和 `.ltx` 均属于同一工程。新增或修改
ILA/VIO 后，必须重新构建，并使用该次实现产生的匹配镜像。

## 执行与记录

Hardware Manager 状态和原生 `.ila` 数据保留在 `<工程>.hw/`。启动前只检查 AI 本次
要使用的精确硬件工作区是否被占用；打开 Vivado GUI 不构成冲突。目标工作区确实被占用
时停止并汇报。

AI 在 `out/ila/` 或 `out/hardware/` 中记录镜像与 LTX 路径、目标和核标识、捕获或写入
条件、观察结论及原生 `.ila` 路径。ILA 结论仅覆盖指定镜像、时段和探针。

JTAG 下载默认是易失配置，除非计划明确要求非易失操作。

用户明确要求的独立硬件操作，在 `AI-work/hardware/<标识>/` 创建 `PLAN.md`、
`EXECUTION.md` 和 `ACCEPTANCE.md`；若需要新增或修改 RTL、XDC、IP、ILA、VIO、
Block Design 或工程设置，则进入 Mode 3。

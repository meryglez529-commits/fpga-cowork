# H — Vivado 硬件、ILA 与 VIO

H 用于通过用户指定 `.xpr` 的 Hardware Manager 完成 JTAG 枚举、易失下载、ILA 捕获、
VIO 操作或非易失配置。硬件会话沿用同一工程的器件、实现结果和调试核上下文。

## 准备

1. 打开用户指定的 `.xpr` 并进入 Hardware Manager。
2. 枚举实际 JTAG target 和 device，核对目标标识与 FPGA part；存在多个候选时，请用户
   指定目标或依据已经确认的唯一身份选择。
3. 按本次 H 目标准备所需输入：仅枚举 target/device 或读取现有状态时无需镜像；下载需要
   `.bit`；ILA/VIO 需要同一次实现生成的匹配 `.bit` 和 `.ltx`。对需要镜像的操作，核对
   implementation run、`.bit` 和 `.ltx` 是否对应当前 RTL、XDC、IP、Block Design 与
   ILA/VIO 设计，并核对调试核、`CELL_NAME` 和 probe 宽度。输入缺失或结果过期时，报告
   缺口并停止该项硬件操作。
4. 明确本次下载、触发、采集、VIO 值或配置存储器操作，以及预期观察和结束条件。
5. 检查本次使用的硬件工作区和输出文件没有被其他会话占用；为新采集使用可辨识的唯一
   文件名，保留历史结果。

确定当前目标需要硬件操作后，按本次请求执行 H。JTAG 下载按易失配置处理；模块设计或
用户请求明确包含非易失配置时，按指定器件、镜像和地址执行 Flash 操作。

## 执行

需要下载时，在 Hardware Manager 中为精确 device 设置并校验 `PROGRAM.FILE`。需要
ILA/VIO 时，使用与 bitstream 来自同一次 implementation 的 LTX。使用 Vivado 2021.1 时，
每次建立或更新 LTX 关联都必须将 `PROBES.FILE` 和 `FULL_PROBES.FILE` 同时设置为同一个
标准化路径。下载前设置并读回 `PROGRAM.FILE` 和两个 probes 属性；下载后重新设置两个
probes 属性，并通过 `refresh_hw_device -update_hw_probes` 显式加载本次 LTX。

```tcl
set bit_path [file normalize $bit_path]
set ltx_path [file normalize $ltx_path]

set_property PROGRAM.FILE     $bit_path $device
set_property PROBES.FILE      $ltx_path $device
set_property FULL_PROBES.FILE $ltx_path $device

# 下载前读回并校验三个路径
program_hw_devices $device

set_property PROBES.FILE      $ltx_path $device
set_property FULL_PROBES.FILE $ltx_path $device
refresh_hw_device -update_hw_probes $ltx_path $device
```

刷新后重新读回两个 probes 属性，并核对目标 device 上 ILA/VIO 的数量、`CELL_NAME`、probe
名称和宽度。任一项与本次设计不符时停止触发或采集，不能沿用 Hardware Manager 中已有的
调试对象。

同一个板级验证批次复用一次 Hardware Manager/JTAG 会话和已经下载的匹配镜像，在会话内
连续完成所需的触发设置、重新 arm、采集、导出和 VIO 操作。修改 Hardware Manager 中的
触发条件、比较值、触发位置、采集次数或导出设置时，继续使用当前镜像。修改 RTL、XDC、
IP、Block Design，或者改变 ILA/VIO 的核结构、probe 连接、宽度、数量、采样深度或时钟时，
将当前 bitstream 和 LTX 视为过期。同一板级验证批次内不为每个触发或采集参数重复创建
会话或下载。

ILA 使用明确的 probe、比较条件、触发位置、采样深度和有限等待时间。VIO 操作使用明确的
对象和值，并读回可观察状态。原生 `.ila` 和需要的采样导出保存在 `<工程>.hw/`。

执行中如果 target/device 身份、FPGA part、bit/LTX 或调试核不匹配，保持现有硬件状态并
向用户报告需要校正的对象。目标工作区正在被其他硬件会话使用时，等待或说明冲突。

## 结果

向用户报告：

- `.xpr`、JTAG target、device 和 part；
- 使用的 `.bit`、`.ltx`、实现 run 及其可检查身份；
- 实际执行的下载、触发、采集、VIO 或 Flash 操作；
- 原生 `.ila`、采样导出或 Hardware Manager 工作区的绝对路径；
- 当前板卡保留的配置状态；
- 结论对应的镜像、调试核、probe、触发条件和采样窗口。

硬件结果只证明本次连接、镜像和观察范围内的板级行为。

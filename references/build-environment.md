# B — Vivado 构建

B 用于在用户指定的 `.xpr` 中执行综合、实现、时序分析、DRC 或 bitstream 生成。构建
沿用工程已登记的源、约束、IP、Block Design、top 和 run，使结果可在 GUI 中直接查看。

## 准备

1. 打开用户指定的 `.xpr`，确认当前工程路径、器件、top 和 compile order。
2. 确认本次设计使用的 RTL、XDC、IP、Block Design、ILA/VIO 已登记并保存；既有 XDC
   继续作为工程输入，针对本次新增或改变的接口确认相关约束。
3. 明确目标 synthesis/implementation run，以及需要到达的阶段和评价指标。
4. 检查目标 run 的状态，以及已有结果是否对应当前 RTL、XDC、IP、Block Design 和
   ILA/VIO 设计。结果仍匹配且满足本次目标时直接复用；结果过期时，从最早受影响的阶段
   重新运行。
5. 检查目标 run 没有被其他 Vivado 进程执行。GUI 仅处于打开状态时可以继续；run 正在
   运行时等待或向用户说明冲突。

设计输入发生变化只会使既有结果可能过期，不单独触发 B。确定当前目标需要构建后，先汇总
当前一轮相关修改，尽量用一次构建覆盖同一批修改。根据目标选择最低必要阶段：综合检查
运行到 synthesis；实现、时序或 DRC 检查运行到相应 implementation 阶段；生成镜像时
运行到 bitstream，并产生该实现包含的 debug probes。若构建目标未明确，先说明各阶段的
耗时与产物，再确定运行阶段。

## 执行

使用工程现有 run 完成目标阶段，并等待 run 得到明确的最终状态。原生日志、检查点、报告、
`.bit` 和 `.ltx` 保留在 `<工程>.runs/`。需要补充报告时，将报告写入对应 run 的工程目录，
方便用户从 GUI 和文件系统共同检查。

根据交付目标检查：

- synthesis/implementation run 的完成状态；
- Error、Critical Warning 及与用户逻辑相关的 Warning；
- IO、clock、route status 和适用的 DRC；
- 时序约束覆盖，以及 WNS/TNS、WHS/THS 等适用指标；
- bitstream 和 debug probes 是否来自本次 implementation run。

Warning 按其对当前模块和交付目标的实际影响解释。无有效时序路径或约束覆盖不足时，直接
说明该限制，不用无意义的数值替代结论。

## Run 中断与恢复

Project Mode 的 `launch_runs` 启动 synthesis 或 implementation run 后，外层控制进程与
实际 run 工作进程分别存在。等待命令暂时返回 session ID 或转入后台不表示流程已经中断，
应继续等待原调用，不得启动第二次 run。

外层控制进程异常结束，或者 run 长时间残留为 Running 时，先确定受影响的具体 run，并检查
run 目录中的状态文件以及其中记录的工作进程 Host/PID。检查完成前，不把 run 假定为仍在
运行或已经停止，也不执行 reset 或重新 launch。

- 工作进程仍存在时，继续等待或按用户要求终止；不得 reset 或重复启动。
- 工作进程已经不存在、run 又没有正常结束状态时，将其视为异常残留。
- 恢复时只 reset 精确受影响的 run。implementation 异常不应无条件 reset 已完成且仍有效
  的 synthesis run。
- reset 无法删除生成文件时，先定位残留进程或文件占用；占用解除前不得重新 launch。
- 恢复运行后，只分析当前轮次对应的日志范围。`runme.log` 中较早轮次的 Error、Critical
  Warning 或 Vivado 会话不得作为当前轮次失败依据。

## 结果

向用户报告：

- `.xpr`、top、使用的 run 和最终状态；
- DRC、时序、路由及相关警告的结论；
- 关键报告、`.bit` 和 `.ltx` 的绝对路径；
- 交付镜像的哈希或其他可检查身份；
- 构建结果尚未覆盖的功能或板级行为。

构建成功证明当前工程输入满足所检查的构建指标；功能行为继续由相应的仿真或板级证据说明。

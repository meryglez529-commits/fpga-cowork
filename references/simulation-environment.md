# S — 仿真

S 用于获得明确 DUT 和场景的仿真证据。它始终使用用户指定 `.xpr` 的 simulation
fileset 和工程上下文。

## 计划

在工作包计划中写明：

- `.xpr`、simulation fileset、DUT、testbench 和场景；
- 检查方法与通过标准；
- `$finish`、仿真 runtime 或其他明确终止条件；
- 是否需要新增 testbench、登记文件或调整 simulation top。

testbench 位于该工程已选 simulation fileset 的 GUI 标准源目录，通常为
`<工程>.srcs/<fileset>/new/`。新增源文件、登记至 fileset 或调整 top 会改变工程状态，
必须属于已确认计划。

## 执行与记录

通过既有 `.xpr` 启动仿真。WDB、WCFG、XSim 日志和其他原生产物留在 `<工程>.sim/`。
在启动前只检查本次要使用的精确仿真输出是否被占用；单纯打开 Vivado GUI 不构成冲突。
若目标输出确实被占用，停止并汇报。

AI 在工作包 `out/sim/` 中记录 testbench、场景、命令、结论和原生产物绝对路径。仿真
通过仅覆盖实际执行的场景，不能替代构建或板级验证。

用户明确要求的独立仿真操作，在 `AI-work/sim/<标识>/` 创建 `PLAN.md`、
`EXECUTION.md` 和 `ACCEPTANCE.md`，记录同样的信息；若需要修改设计输入或工程设置，
则进入 Mode 3。

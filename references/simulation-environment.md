# S — Vivado 仿真

S 用于在用户指定的 `.xpr` 中获得明确 DUT 和场景的仿真证据。仿真沿用工程已登记的
simulation fileset、源文件、IP、compile order 和 simulation top，使命令行执行结果与
GUI 中的工程状态一致。

## 准备

1. 打开用户指定的 `.xpr`，确认当前工程路径、器件和目标 simulation fileset。
2. 明确 DUT、testbench、测试场景、检查方法和通过条件。
3. 确认 RTL、仿真源、IP 和 testbench 已登记到正确 fileset；新增内容沿用工程的源文件
   布局，更新 compile order 并保存工程。
4. 选择 `$finish`、有限 runtime 或测试框架终止条件，使仿真能够明确结束。
5. 检查本次使用的具体仿真会话或输出没有被其他进程占用。Vivado GUI 仅处于打开状态时，
   继续使用这份工程；实际仿真会话正在使用同一输出时，等待或向用户说明冲突。

## 执行

通过该 `.xpr` 的 project-mode 仿真流程启动仿真，使用工程当前的 simulation top 和
fileset 设置。将批处理 log/journal 明确放在工程目录或工程内的运行目录。

优先使用能够自动判定结果的 testbench。检查模拟器退出状态、断言、错误信息和预期终止
标记；需要观察波形时，使用同一会话产生的 WDB/WCFG。

WDB、WCFG、XSim 输出和其他仿真原生产物保留在 `<工程>.sim/`。

## 结果

向用户报告：

- `.xpr`、simulation fileset、top、DUT 和 testbench；
- 实际执行的场景及通过/失败结果；
- 原生仿真目录、日志和波形的绝对路径；
- 仿真实际覆盖的行为和仍未验证的内容。

仿真结果只证明实际执行的 testbench 和场景。只有出现明确通过条件时才报告通过；失败时
保留首个有效错误及其原生路径，供后续诊断。

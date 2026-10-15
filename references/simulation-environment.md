# S — Vivado 仿真

在用户指定的 `.xpr` 中获得明确 DUT 和场景的仿真证据，沿用工程的 simulation fileset、
源、IP、compile order 和 simulation top。

## 准备

明确 DUT、testbench、场景、检查方法和通过条件，以及有限 runtime、`$finish` 或测试框架
结束条件。确认目标 fileset、top 和相关输入登记正确，更新必要的 compile order 并保存工程。

确认本次仿真输出未被实际运行的会话占用。

## 执行

通过该工程的 project-mode 仿真流程运行目标场景，优先使用可自动判定结果的 testbench。
检查退出状态、断言、错误信息和预期结束标记。

完整保存本次生成的 WDB、WCFG 和 XSim 输出及其关联文件，沿用 `<工程>.sim/`；
波形与本次仿真结果对应。

## 结果

按任务报告所用工程、fileset、top、DUT/testbench、实际场景与结果，以及日志和波形入口。
说明实际覆盖范围；只有满足明确通过条件时报告通过。失败时保留有效错误及其原生路径。

# <UNIT> 仿真复现说明

> 本文件给用户使用：用项目级 runner 重跑仿真，并在结果产生后打开波形。此处不提供裸 `xsim`、手工编译或 GUI 点击作为验收路径。

项目级仿真环境 SOP：`AI-work/env/SIMULATION.md`（或项目指定的 `AI-work/guide/VIVADO_SIM_SOP.md`）

## 0. Preflight

| 项 | 值 |
|---|---|
| 已读取项目级 SOP | `AI-work/env/SIMULATION.md` / `AI-work/guide/VIVADO_SIM_SOP.md` |
| 复用的黑匣子 runner | `<skill>/scripts/templates/run_sim.tcl` |
| 当前 unit root | `AI-work/features/<feature-slug>/<UNIT>` |
| 本次输出目录 | `AI-work/features/<feature-slug>/<UNIT>/out/sim/<run-id>`（新建、AI-owned；仅保存调用日志与结果摘要） |
| 允许的项目 sim set | `sim_1`（或项目记录的名称） |
| 已知阻塞 | `<SIM_OUTPUT_LOCKED / SIM_FIXTURE_BLOCKED / 无>` |

## 1. 本次仿真验证什么

<说明验证目标、覆盖边界和不覆盖的风险。>

## 2. testbench、oracle 和 fixture map

| 项 | 值 |
|---|---|
| 工程 | `<project.xpr>` |
| 仿真器 | Vivado project simulation manager / XSim |
| testbench | `<path/to/tb.v>` |
| 仿真 top | `<tb_top>` |
| DUT | `<path/to/dut.v>` |
| 有限运行时长 | `<e.g. 10us>` |
| oracle | `sim/oracle.tcl`；`sim_oracle` 必须仅返回 `1`（通过）或 `0`（失败） |
| fixture adapter | `sim/fixture-stage.tcl` 或 `N/A` |

### Fixture map（仅文件驱动 stimulus）

| Fixture | Source | SHA-256 | 格式/宽度 | XSim 目标路径 |
|---|---|---|---|---|
| | | | | `<project>.sim/<simset>/behav/xsim/<name>` |

## 3. Batch / PowerShell 重跑

先创建新的 run 目录，然后一次性执行下面命令。runner 会在既有 sim set 中保留 testbench membership、selected top 和有限运行时长，直接复用项目的 XSim 工作目录、在时间推进前调用 fixture adapter、执行 oracle，并保存与本轮 WDB 同名的 WCFG；WDB、WCFG 和 XSim 日志均只保留在项目 XSim 目录。

```powershell
$run = 'AI-work\features\<feature-slug>\<UNIT>\out\sim\<run-id>'
New-Item -ItemType Directory $run | Out-Null
& "<VIVADO_BAT>" -mode batch `
  -source <skill>\scripts\templates\run_sim.tcl `
  -log "$run\vivado.log" -journal "$run\vivado.jou" `
  -tclargs <project.xpr> <tb.v> <tb_top> <bounded-runtime> $run `
           AI-work\features\<feature-slug>\<UNIT>\sim\oracle.tcl `
           AI-work\features\<feature-slug>\<UNIT>\sim\fixture-stage.tcl sim_1
```

When no file-backed fixture is used, pass `-` in the fixture position. When no
oracle is used, pass `-` in the oracle position. Omit the final `sim-set`
argument only for the default `sim_1`; for a non-default set, pass its name in
the eighth position.

## 4. 测试用例

| TC | 验证点 | 预期 | Oracle evidence |
|---|---|---|---|
| TC1 | | | |

## 5. 重点信号

| 信号 | 你要确认什么 |
|---|---|
| `<signal>` | |

## 6. 通过标准

| 项 | 通过条件 |
|---|---|
| runner | 退出码为 0 且 outer log 出现 `RESULT: SIM_PASS` |
| oracle | `sim_oracle` 返回精确值 `1` |
| evidence | 当前 run 目录具有 `SIMULATION_RESULT.txt` 与 `vivado.log`；其中记录的项目 XSim 目录具有同名的 `<snapshot>.wdb` / `<snapshot>.wcfg` |
| waveform | 在项目 XSim 目录中检查关键窗口和边界是否符合第 4/5 节 |

## 7. GUI 波形检查（验收完成后）

```tcl
source AI-work/features/<feature-slug>/<UNIT>/sim/run_gui.tcl
```

将 `run_gui.tcl` 中的 WDB 路径替换为 `SIMULATION_RESULT.txt` 记录的项目本地 WDB；脚本会由其 basename 自动得到同名 WCFG。此步骤只打开证据，不重新运行仿真。

## 8. AI 已生成的结果

| 产物 | 路径 | 说明 |
|---|---|---|
| runner verdict | `out/sim/<run-id>/vivado.log` | `RESULT: ...` |
| outer log/journal | `out/sim/<run-id>/vivado.log`, `vivado.jou` | Vivado 完整调用记录 |
| simulation logs | `<project>.sim/<sim-set>/behav/xsim/{compile,elaborate,simulate}.log` | 项目本地 XSim 输出，不复制 |
| waveform | `<project>.sim/<sim-set>/behav/xsim/<snapshot>.{wdb,wcfg}` | runner 保留 WDB，并保存同 basename 的 WCFG |

## 9. 未覆盖场景

| 场景 | 未覆盖原因 | 后续建议 |
|---|---|---|
| | | |

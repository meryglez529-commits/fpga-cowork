# Verilog 代码风格规范

AI 生成和修改手写 RTL 时采用以下约定。接口行为、输出周期及资源选择由设计确定。
修改既有模块时保留外部接口名称；厂商 IP 的模块和端口名称沿用其定义。

## 1 命名与信号声明

| 对象 | 约定 | 示例 |
| --- | --- | --- |
| 文件、模块、函数 | 小写下划线；模块与文件同名，名称表达功能 | `payload_buffer.v`、`payload_buffer` |
| 输入、输出、双向端口 | `_i`、`_o`、`_io` | `payload_i`、`valid_o`、`pad_io` |
| 内部寄存信号 | `_reg`；流水级号放在后缀前 | `count_reg`、`payload_s1_reg` |
| 内部组合信号 | `_wire` | `selected_wire`、`accept_wire` |
| 时钟、低有效复位 | `clk`、`rst_n`；多时钟域加域名 | `clk_core`、`rst_n_core` |
| 其他低有效信号 | `_n` 放在类型或方向后缀前 | `irq_n_o`、`enable_n_wire` |
| parameter、localparam、宏 | 大写下划线，名称表达含义 | `DATA_WIDTH`、`FIFO_DEPTH` |
| 子模块实例、generate 块 | 小写下划线，分别加 `u_`、`gen_` | `u_payload_buffer`、`gen_lane` |

- 时钟和复位采用固定命名；其他端口使用方向后缀，内部信号使用角色后缀。
- `_reg/_wire` 按电路角色区分：组合 always 中声明为 reg 的变量仍命名为 `selected_wire`。
- assign 或子模块驱动的信号声明为 wire；always 内赋值的变量声明为 reg。输出端口以 `_o` 结束，不叠加内部角色后缀。
- 所有信号显式声明，内部信号每行一个；wire 不在声明处赋值，组合表达式在逻辑区使用 assign。
- 每个信号只有一处驱动，不由多个 always、assign 或实例共同写入。

## 2 文件、模块组织与排版

- 可综合 RTL 使用 Verilog-2001；模块文件为 `.v`，公共头文件为 `.vh`，一文件一模块。
- 端口使用 ANSI 声明，每行一个端口，写明方向、类型和位宽；时钟复位在前，其余按接口分组。
- 模块顺序固定为：参数和端口 → 局部常量、函数及信号声明 → 子模块实例 → 逻辑实现。
- 缩进使用 4 个空格，不用 Tab；每行最多 100 字符，不留行尾空格，文件以换行结束。
- 相邻逻辑块空一行；功能区用简短分隔线注释标明用途，如 `// ---- 次态计算 ----`。
- 二元运算符两侧、逗号后留空格；数据向量按降序声明，最低位为 0，如 `[DATA_WIDTH-1:0]`；复杂表达式用括号明确分组。
- 长表达式在运算符前换行，续行多缩进一级；声明、赋值和连接仅在本组内对齐。
- 参数使用命名覆盖，端口使用命名连接；每行一个连接，按声明顺序排列，并按接口空行分组。
- 例化处以连接为主；复杂运算或条件表达式先形成命名的 `_wire` 信号。定宽常量、简单切片和拼接可直接连接。
- 未使用的输入按接口约定接定宽合法值；未使用的输出显式空接并注释，不省略端口或另建无用途的中间信号。

~~~verilog
payload_buffer #(
    .DATA_WIDTH (16)
) u_payload_buffer (
    .clk        (clk),
    .rst_n      (rst_n),

    .enable_i   (1'b1),
    .payload_i  (payload_i),
    .payload_o  (buffered_wire),
    .status_o   () // 不使用状态输出。
);
~~~

## 3 组合逻辑与条件语句

- 单个表达式使用 assign，简单二选一使用 `?:`；多路等值选择使用普通 case，有优先级的条件使用 if/else if，不嵌套三元表达式。
- 组合过程使用 `always @(*)` 和阻塞赋值 `=`。
- 过程开头给所有结果默认值，再按条件覆盖；中间量先计算再使用，每条执行路径都有确定赋值。
- 组合量不通过自赋值保持，不形成锁存器或组合反馈。
- if、else、case 分支和循环体都使用 begin/end，即使只有一条语句；else 与前面的 end 同行。
- case 包含 default，明确未匹配时的结果；各分支比 case 缩进一级，分支内容再缩进一级。
- 不使用 casex；casez 仅用于明确需要通配匹配的译码，通配位写为 `?`。不用 full_case/parallel_case 指示代替完整赋值。

~~~verilog
reg [7:0] selected_wire;

always @(*) begin
    selected_wire = 8'd0;

    case (select_i)
        2'd0: begin
            selected_wire = payload_i;
        end
        2'd1: begin
            selected_wire = alternate_i;
        end
        default: begin
            selected_wire = 8'd0;
        end
    endcase
end
~~~

## 4 时序逻辑

- 时序过程使用非阻塞赋值 `<=`，赋值不带 `#` 延时；一个过程只使用一个工作时钟。
- 同一功能内、时钟和复位条件相同的寄存器可以在同一块中更新；不同工作时钟或复位条件分块处理。
- 右侧表达式读取更新前的寄存值，不依靠语句顺序将本沿的新值传给后续赋值。
- 保持型寄存器在未使能时省略赋值，不写 `length_reg <= length_reg;`。
- 单拍脉冲每拍更新，事件发生时置位，其余周期清零，不使用保持型寄存器的写法。

~~~verilog
always @(posedge clk) begin
    if (!rst_n) begin
        length_reg <= 8'd0;
    end else if (load_i) begin
        length_reg <= length_i;
    end
end
~~~

## 5 复位

- 同步或异步复位按设计要求确定，沿用工程和 IP 的复位约定。
- 同步复位使用 `always @(posedge clk)`；异步复位使用 `always @(posedge clk or negedge rst_n)`。
- 复位分支放在过程首位，优先于使能，复位值写明位宽；复位对象和数值按设计确定，无复位要求的寄存器不添加复位分支。
- 使用异步复位时，释放必须同步到所在时钟域；各时钟域分别处理，不使用其他域的同步结果。
- 外部异步复位命名为 `rst_n_async`，处理后的本域低有效复位命名为 `rst_n`。功能模块直接使用已有本域复位，不重复建立同步链。

需要将外部异步复位处理为本域异步断言、同步释放时，优先复用工程中的复位同步模块。
手写同步链采用以下形式，并在 Vivado 中标记 ASYNC_REG：

~~~verilog
// 外部复位断言时不等待时钟；释放需经过两个 clk 上升沿。
(* ASYNC_REG = "TRUE" *) reg [1:0] rst_sync_reg;

always @(posedge clk or negedge rst_n_async) begin
    if (!rst_n_async) begin
        rst_sync_reg <= 2'b00;
    end else begin
        rst_sync_reg <= {rst_sync_reg[0], 1'b1};
    end
end

assign rst_n = rst_sync_reg[1];
~~~

## 6 FSM

统一采用三段式，按以下顺序组织：

| 部分 | 固定写法 |
| --- | --- |
| 状态寄存 | 时序块仅更新当前状态 `state_reg`，复位进入初始状态 |
| 次态计算 | 独立组合块仅计算 `next_state_wire`，开头默认 `next_state_wire = state_reg;` |
| 输出与动作 | 组合输出用 assign 或独立组合块；寄存输出和数据更新用时序块 |

- 状态常量使用定宽 localparam 和 `ST_` 前缀，如 `ST_IDLE`、`ST_RUN`；当前状态与次态位宽一致。
- 多个 FSM 加功能前缀，如 `rx_state_reg`、`rx_next_state_wire`。
- 次态 case 列出所有合法状态，转移条件写在各状态分支内。
- default 明确非法状态的恢复目标，无特殊设计约定时回到初始状态。
- 输出与动作块只更新自身负责的信号；组合输出完整赋值，寄存输出分别表达保持、更新和脉冲行为。
- 输出采用组合或寄存形式按接口约定确定，不能因套用三段式改变输出生效周期。

## 7 参数、常量与位宽

- 可配置量使用 parameter，模块内派生量和固定常量使用 localparam；宏用于公共定义和条件编译。
- 数据常量写明位宽，如 `8'd0`、`16'h00ff`；尺寸、数量和循环边界使用描述性参数。
- 明确操作数、结果及目标信号的位宽；保留进位时先扩展操作数，并声明足够宽的结果。
- 有符号和无符号数据混合运算前，先统一符号属性；补零、符号扩展和截取均显式表达。
- 乘积按完整精度声明，两个 N 位数的完整乘积最多需要 2N 位；使用部分结果时显式切片，如 `product_wire[15:8]`。
- 比较常量与被比较数据的位宽和符号属性保持一致，不依赖隐式截断完成取低位或回绕。

## 8 注释与模板使用

- 注释使用 `//`。模块头按“功能、时钟复位、周期”组织，说明用途、时钟域、复位条件及输入接收到输出有效的周期关系。
- 声明旁说明参数的范围和单位、端口的编码与有效条件、状态的职责，以及关键寄存器保存的内容和更新时机；不重复声明已有的方向和位宽。
- 关键逻辑前说明设计原因、时序关系和边界处理，不逐句翻译简单代码。
- 简短说明放在行尾，多行说明放在对应声明或逻辑之前；同一信息放在最相关的位置，避免反复解释。
- 修改接口、功能、时序、复位或位宽时，同步更新相关注释，保证描述与当前代码一致。
- 同类模块、实例、组合过程、时序过程及 FSM 沿用本规范的组织方式；按实际接口和设计条件填写信号、位宽和复位值。

## 9 完整模块示例

以下请求计算器集中展示模块组织、信号命名、三段式 FSM、组合与时序逻辑、复位及位宽处理。
本例使用本域同步复位；子模块连接和外部异步复位处理等写法见前面对应章节。

~~~verilog
// 文件：request_calculator.v
// 功能：对有符号 A 与无符号 B 执行加、减、乘，结果保留完整精度。
// 时钟复位：clk 上升沿采样；rst_n 是上级提供的本域低有效同步复位。
// 周期：空闲时在 N 沿锁存请求，N+1 沿后结果和 done_o 有效一拍，同时回到空闲。
//       start_i 持续为 1、模式有效且未取消时，每两拍接收一次请求。
module request_calculator #(
    parameter DATA_WIDTH = 8 // 输入位宽，单位为 bit，至少为 1。
) (
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire                         start_i,    // 空闲时采样，忙时忽略。
    input  wire                         cancel_n_i, // 采样沿为 0 时取消，优先于接收和完成。
    input  wire [1:0]                   mode_i,     // 0：加；1：减；2：乘；3：无效请求。

    input  wire signed [DATA_WIDTH-1:0] operand_a_i,
    input  wire        [DATA_WIDTH-1:0] operand_b_i,

    output wire                             busy_o,  // 运算中为 1，不能接收新请求。
    output wire                             done_o,  // 完成脉冲，持续一个 clk 周期。
    output wire signed [2*(DATA_WIDTH+1)-1:0] result_o // done_o 为 1 时有效，其余周期为零。
);

    // ---- 局部常量与信号声明 ----
    localparam integer EXT_WIDTH    = DATA_WIDTH + 1; // B 补零后转换为非负的有符号数。
    localparam integer SUM_WIDTH    = EXT_WIDTH + 1;  // 加减再扩展一位，保留进位和负数结果。
    localparam integer RESULT_WIDTH = 2 * EXT_WIDTH; // 容纳两个 EXT_WIDTH 位数的完整乘积。

    localparam [1:0] ST_IDLE = 2'd0; // 等待并锁存请求。
    localparam [1:0] ST_CALC = 2'd1; // 使用锁存的输入运算，在下一沿提交结果。

    localparam [1:0] MODE_ADD = 2'd0;
    localparam [1:0] MODE_SUB = 2'd1;
    localparam [1:0] MODE_MUL = 2'd2;
    localparam signed [RESULT_WIDTH-1:0] ZERO_RESULT = {RESULT_WIDTH{1'b0}};

    wire accept_wire;
    wire finish_wire;

    reg [1:0] state_reg;
    reg [1:0] next_state_wire;
    reg [1:0] mode_reg;        // 与操作数同时锁存，完成前保持本次运算模式。
    reg       done_reg;        // 与结果同沿提交，返回空闲时仍有效一拍。

    // 锁存本次请求，避免运算期间输入变化影响结果。
    reg  signed [DATA_WIDTH-1:0]   operand_a_reg;
    reg         [DATA_WIDTH-1:0]   operand_b_reg;
    wire signed [EXT_WIDTH-1:0]    operand_a_ext_wire;
    wire signed [EXT_WIDTH-1:0]    operand_b_ext_wire;
    wire signed [SUM_WIDTH-1:0]    sum_wire;
    wire signed [SUM_WIDTH-1:0]    difference_wire;
    wire signed [RESULT_WIDTH-1:0] product_wire;
    reg  signed [RESULT_WIDTH-1:0] calculated_wire;
    reg  signed [RESULT_WIDTH-1:0] result_reg; // 保存最近一次完成结果，下一次完成时覆盖。

    // ---- 请求接收与完成条件 ----
    // 取消同时关闭接收与完成，避免在取消沿产生 done_o。
    assign accept_wire = rst_n && cancel_n_i && (state_reg == ST_IDLE)
        && start_i && (mode_i <= MODE_MUL);
    assign finish_wire = rst_n && cancel_n_i && (state_reg == ST_CALC);

    // ---- 状态寄存 ----
    always @(posedge clk) begin
        if (!rst_n) begin
            state_reg <= ST_IDLE;
        end else begin
            state_reg <= next_state_wire;
        end
    end

    // ---- 次态计算 ----
    always @(*) begin
        next_state_wire = state_reg;

        if (!cancel_n_i) begin
            next_state_wire = ST_IDLE;
        end else begin
            case (state_reg)
                ST_IDLE: begin
                    if (accept_wire) begin
                        next_state_wire = ST_CALC;
                    end
                end
                ST_CALC: begin
                    next_state_wire = ST_IDLE;
                end
                default: begin
                    // 非法状态中止本次请求，恢复空闲时不报告完成。
                    next_state_wire = ST_IDLE;
                end
            endcase
        end
    end

    // ---- 组合运算与结果选择 ----
    // 拼接结果默认无符号，用 $signed 明确属性，避免无符号 B 改变负数 A 的运算含义。
    assign operand_a_ext_wire = $signed({operand_a_reg[DATA_WIDTH-1], operand_a_reg});
    assign operand_b_ext_wire = $signed({1'b0, operand_b_reg});
    assign sum_wire = $signed({operand_a_ext_wire[EXT_WIDTH-1], operand_a_ext_wire})
        + $signed({operand_b_ext_wire[EXT_WIDTH-1], operand_b_ext_wire});
    assign difference_wire = $signed({operand_a_ext_wire[EXT_WIDTH-1], operand_a_ext_wire})
        - $signed({operand_b_ext_wire[EXT_WIDTH-1], operand_b_ext_wire});
    assign product_wire = operand_a_ext_wire * operand_b_ext_wire;

    always @(*) begin
        calculated_wire = ZERO_RESULT;

        case (mode_reg)
            MODE_ADD: begin
                calculated_wire = $signed(
                    {{(RESULT_WIDTH-SUM_WIDTH){sum_wire[SUM_WIDTH-1]}}, sum_wire});
            end
            MODE_SUB: begin
                calculated_wire = $signed(
                    {{(RESULT_WIDTH-SUM_WIDTH){difference_wire[SUM_WIDTH-1]}}, difference_wire});
            end
            MODE_MUL: begin
                calculated_wire = product_wire;
            end
            default: begin
                calculated_wire = ZERO_RESULT;
            end
        endcase
    end

    // ---- 输出与时序动作 ----
    always @(posedge clk) begin
        if (!rst_n) begin
            done_reg <= 1'b0;
        end else begin
            // 完成后的下一拍清零，保证脉冲不会因寄存器保持而延长。
            done_reg <= finish_wire;
        end
    end

    // 操作数和结果均在各自有效前写入；无效输出被屏蔽，数据寄存器无需复位。
    always @(posedge clk) begin
        if (accept_wire) begin
            mode_reg      <= mode_i;
            operand_a_reg <= operand_a_i;
            operand_b_reg <= operand_b_i;
        end else if (finish_wire) begin
            result_reg <= calculated_wire;
        end
    end

    assign busy_o   = (state_reg != ST_IDLE);
    assign done_o   = done_reg;
    assign result_o = done_reg ? result_reg : ZERO_RESULT;

endmodule
~~~

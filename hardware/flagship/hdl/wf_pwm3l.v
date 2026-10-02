// wf_pwm3l.v -- three-level four-switch buck-boost modulator with dead-time insertion.
//
// REFERENCE ONLY -- simulate and review before use (tb_wf_pwm3l.v, `make hdl`).
// Target: a small FPGA such as a Lattice iCE40UP5K. At 48 MHz one count is
// 20.8 ns, which is coarse for dead time; a production design would use a
// microcontroller high-resolution timer (STM32G474 HRTIM, ~184 ps) or an FPGA
// with DDR/IDELAY output stages. The logic below is resolution-agnostic.
//
// Gate map: g[1]=Q1 outer-top  g[2]=Q2 inner-top  g[3]=Q3 inner-bottom  g[4]=Q4 outer-bottom  (input leg)
//           g[5]=Q5 outer-top  g[6]=Q6 inner-top  g[7]=Q7 inner-bottom  g[8]=Q8 outer-bottom  (output leg)
//           g_in  = bidirectional GaN input disconnect, g_bp = bidirectional GaN bypass switch
//
// Modes: 0 OFF, 1 BUCK, 2 BUCKBOOST, 3 BOOST, 4 BYPASS
// Guarantees (checked by the testbench):
//   * complementary pairs (Q1/Q4, Q2/Q3, Q5/Q8, Q6/Q7) are never on together and are both off
//     for at least dt counts at every transition,
//   * the bypass switch is only on after every leg gate has been off for dt counts,
//   * fault_n low forces every gate off combinationally and latches until reset.

module wf_pwm3l #(
    parameter W = 12
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         fault_n,
    input  wire [2:0]   mode_in,
    input  wire [W-1:0] period_in,   // counts per switching period (even, >= 4*dt)
    input  wire [W-1:0] d1_in,       // input-leg top on-time, counts (each of Q1 and Q2)
    input  wire [W-1:0] d2_in,       // output-leg bottom on-time, counts (each of Q8 and Q7)
    input  wire [W-1:0] phase_in,    // output-leg carrier phase, counts
    input  wire [W-1:0] dt_in,       // dead time, counts
    output wire [8:1]   g,
    output wire         g_in,
    output wire         g_bp
);
    localparam OFF = 3'd0, BUCK = 3'd1, BB = 3'd2, BOOST = 3'd3, BYPASS = 3'd4;

    // ---------------------------------------------------------------- shadow registers
    reg [2:0]   mode;
    reg [W-1:0] per, d1, d2, ph, dt, half;
    reg [W-1:0] cnt;
    wire        wrap = (cnt == per - 1'b1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mode <= OFF; per <= 16; d1 <= 0; d2 <= 0; ph <= 0; dt <= 1; half <= 8; cnt <= 0;
        end else begin
            if (wrap || mode == OFF) begin
                // updates take effect only at a period boundary (or immediately while OFF)
                mode <= mode_in; per <= period_in; d1 <= d1_in; d2 <= d2_in; ph <= phase_in;
                dt <= dt_in; half <= period_in >> 1;
                cnt <= 0;
            end else begin
                cnt <= cnt + 1'b1;
            end
        end
    end

    // ---------------------------------------------------------------- carrier windows
    function [W-1:0] modsub(input [W-1:0] a, input [W-1:0] b, input [W-1:0] p);
        modsub = (a >= b) ? (a - b) : (a + p - b);
    endfunction

    wire in_active  = (mode == BUCK) || (mode == BB);
    wire out_active = (mode == BOOST) || (mode == BB);
    wire run        = (mode == BUCK) || (mode == BB) || (mode == BOOST);

    // command = "top switch wanted"; a static leg holds its tops on
    wire cmd_a = in_active  ? (cnt < d1)                                 : 1'b1; // Q1 vs Q4
    wire cmd_b = in_active  ? (modsub(cnt, half, per) < d1)              : 1'b1; // Q2 vs Q3
    wire cmd_c = out_active ? !(modsub(cnt, ph, per) < d2)               : 1'b1; // Q5 vs Q8
    wire [W:0]   ph_h_raw = {1'b0, ph} + {1'b0, half};
    wire [W-1:0] ph_h     = (ph_h_raw >= {1'b0, per}) ? (ph_h_raw - {1'b0, per}) : ph_h_raw[W-1:0];
    wire cmd_d = out_active ? !(modsub(cnt, ph_h, per) < d2)             : 1'b1; // Q6 vs Q7

    // ---------------------------------------------------------------- dead-time cells
    wire [3:0] top, bot;
    wf_deadtime #(.W(W)) u_a (.clk(clk), .rst_n(rst_n), .en(run), .cmd(cmd_a), .dt(dt), .top(top[0]), .bot(bot[0]));
    wf_deadtime #(.W(W)) u_b (.clk(clk), .rst_n(rst_n), .en(run), .cmd(cmd_b), .dt(dt), .top(top[1]), .bot(bot[1]));
    wf_deadtime #(.W(W)) u_c (.clk(clk), .rst_n(rst_n), .en(run), .cmd(cmd_c), .dt(dt), .top(top[2]), .bot(bot[2]));
    wf_deadtime #(.W(W)) u_d (.clk(clk), .rst_n(rst_n), .en(run), .cmd(cmd_d), .dt(dt), .top(top[3]), .bot(bot[3]));

    // ---------------------------------------------------------------- bypass sequencing
    reg [W-1:0] idle;          // counts since every leg gate went off
    reg         bp_q, in_q;
    wire legs_off = ~|{top, bot};
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            idle <= 0; bp_q <= 1'b0; in_q <= 1'b0;
        end else begin
            idle <= legs_off ? ((idle == {W{1'b1}}) ? idle : idle + 1'b1) : {W{1'b0}};
            bp_q <= (mode == BYPASS) && legs_off && (idle >= dt);
            in_q <= (mode != OFF);
        end
    end

    // ---------------------------------------------------------------- fault latch + outputs
    reg fault_latched;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) fault_latched <= 1'b0;
        else if (!fault_n) fault_latched <= 1'b1;
    end
    wire ok = fault_n & ~fault_latched;

    assign g[1] = ok & top[0];
    assign g[4] = ok & bot[0];
    assign g[2] = ok & top[1];
    assign g[3] = ok & bot[1];
    assign g[5] = ok & top[2];
    assign g[8] = ok & bot[2];
    assign g[6] = ok & top[3];
    assign g[7] = ok & bot[3];
    assign g_bp = ok & bp_q;
    assign g_in = ok & in_q;
endmodule

// A complementary pair with dead time: each side turns on only after the command
// has been stable for dt counts, so both are off for at least dt at every change.
module wf_deadtime #(
    parameter W = 12
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         en,
    input  wire         cmd,
    input  wire [W-1:0] dt,
    output reg          top,
    output reg          bot
);
    reg         last;
    reg [W-1:0] since;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            last <= 1'b0; since <= 0; top <= 1'b0; bot <= 1'b0;
        end else if (!en) begin
            last <= cmd; since <= 0; top <= 1'b0; bot <= 1'b0;
        end else begin
            if (cmd != last) begin
                last <= cmd; since <= 0; top <= 1'b0; bot <= 1'b0;
            end else begin
                if (since != {W{1'b1}}) since <= since + 1'b1;
                // W+1-bit compare: a saturated counter must not wrap to zero
                top <= cmd  && (({1'b0, since} + 1'b1) >= {1'b0, dt});
                bot <= !cmd && (({1'b0, since} + 1'b1) >= {1'b0, dt});
            end
        end
    end
endmodule

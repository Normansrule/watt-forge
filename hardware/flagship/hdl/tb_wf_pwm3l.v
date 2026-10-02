// tb_wf_pwm3l.v -- self-checking testbench for wf_pwm3l (Icarus Verilog).
// Prints "PASS" when every check holds, otherwise "FAIL <n>" with details.
`timescale 1ns/1ps
module tb_wf_pwm3l;
    localparam W = 12;
    reg clk = 0, rst_n = 0, fault_n = 1;
    reg [2:0] mode = 0;
    reg [W-1:0] period = 960, d1 = 0, d2 = 0, phase = 0, dt = 3;
    wire [8:1] g;
    wire g_in, g_bp;
    integer errors = 0;

    wf_pwm3l #(.W(W)) dut (.clk(clk), .rst_n(rst_n), .fault_n(fault_n), .mode_in(mode), .period_in(period),
        .d1_in(d1), .d2_in(d2), .phase_in(phase), .dt_in(dt), .g(g), .g_in(g_in), .g_bp(g_bp));

    always #10.4167 clk = ~clk;   // 48 MHz

    // ---------------- continuous safety monitors
    integer off_a, off_b, off_c, off_d;   // cycles both gates of a pair have been off
    always @(posedge clk) begin
        if (g[1] && g[4]) begin errors = errors + 1; $display("ERR shoot-through Q1/Q4 at %0t", $time); end
        if (g[2] && g[3]) begin errors = errors + 1; $display("ERR shoot-through Q2/Q3 at %0t", $time); end
        if (g[5] && g[8]) begin errors = errors + 1; $display("ERR shoot-through Q5/Q8 at %0t", $time); end
        if (g[6] && g[7]) begin errors = errors + 1; $display("ERR shoot-through Q6/Q7 at %0t", $time); end
        if (g_bp && (|g)) begin errors = errors + 1; $display("ERR bypass on while a leg gate is on at %0t", $time); end
    end

    // dead-time monitor: a pair may only turn a side on after >= dt cycles with both off,
    // unless that same side was the one on before (no transition).
    reg [3:0] prev_top, prev_bot;
    task check_pair(input t_now, input b_now, input t_prev, input b_prev, inout integer off, input [8*6-1:0] name);
        begin
            if (!t_now && !b_now) off = off + 1;
            else begin
                if ((t_now && !t_prev && !b_prev && off < dut.dt) || (b_now && !b_prev && !t_prev && off < dut.dt)) begin
                    errors = errors + 1; $display("ERR dead time %0d < %0d on %0s at %0t", off, dut.dt, name, $time);
                end
                off = 0;
            end
        end
    endtask
    always @(posedge clk) begin
        check_pair(g[1], g[4], prev_top[0], prev_bot[0], off_a, "Q1/Q4 ");
        check_pair(g[2], g[3], prev_top[1], prev_bot[1], off_b, "Q2/Q3 ");
        check_pair(g[5], g[8], prev_top[2], prev_bot[2], off_c, "Q5/Q8 ");
        check_pair(g[6], g[7], prev_top[3], prev_bot[3], off_d, "Q6/Q7 ");
        prev_top <= {g[6], g[5], g[2], g[1]};
        prev_bot <= {g[7], g[8], g[3], g[4]};
    end

    // ---------------- measurement helpers
    integer hi_cnt [1:8];
    integer rise_t [1:8];
    integer k;
    task measure_period;
        integer i, c;
        reg [8:1] last;
        begin
            for (i = 1; i <= 8; i = i + 1) begin hi_cnt[i] = 0; rise_t[i] = -1; end
            // align to period start
            @(posedge clk); while (dut.cnt != 0) @(posedge clk);
            last = g;
            for (c = 0; c < period; c = c + 1) begin
                @(posedge clk);
                for (i = 1; i <= 8; i = i + 1) begin
                    if (g[i]) hi_cnt[i] = hi_cnt[i] + 1;
                    if (g[i] && !last[i] && rise_t[i] < 0) rise_t[i] = c;
                end
                last = g;
            end
        end
    endtask

    task expect_near(input integer got, input integer want, input integer tol, input [8*24-1:0] what);
        begin
            if (got < want - tol || got > want + tol) begin
                errors = errors + 1; $display("ERR %0s: got %0d want %0d +/- %0d", what, got, want, tol);
            end
        end
    endtask

    initial begin
        off_a = 0; off_b = 0; off_c = 0; off_d = 0; prev_top = 0; prev_bot = 0;
        #100 rst_n = 1;
        // ---- BUCK: D1 = 0.8 -> 768 counts
        mode = 1; d1 = 768; d2 = 0; phase = 0; dt = 3;
        repeat (3 * 960) @(posedge clk);
        measure_period;
        expect_near(hi_cnt[1], 768 - 3, 2, "buck Q1 on-time");
        expect_near(hi_cnt[2], 768 - 3, 2, "buck Q2 on-time");
        expect_near(hi_cnt[4], 960 - 768 - 3, 2, "buck Q4 on-time");
        expect_near(hi_cnt[5], 960, 0, "buck static Q5");
        expect_near(hi_cnt[6], 960, 0, "buck static Q6");
        expect_near(hi_cnt[7] + hi_cnt[8], 0, 0, "buck static Q7/Q8 off");
        // phase shift between Q1 and Q2 rising edges: half a period
        expect_near((rise_t[2] - rise_t[1] + 960) % 960, 480, 1, "buck 180 deg phase");
        if (!g_in) begin errors = errors + 1; $display("ERR input disconnect off while running"); end
        // ---- BOOST: D2 = 0.25 -> 240 counts, phase 100
        mode = 3; d2 = 240; phase = 100;
        repeat (3 * 960) @(posedge clk);
        measure_period;
        expect_near(hi_cnt[8], 240 - 3, 2, "boost Q8 on-time");
        expect_near(hi_cnt[7], 240 - 3, 2, "boost Q7 on-time");
        expect_near(hi_cnt[1], 960, 0, "boost static Q1");
        expect_near(hi_cnt[2], 960, 0, "boost static Q2");
        expect_near(hi_cnt[3] + hi_cnt[4], 0, 0, "boost static Q3/Q4 off");
        // ---- long static hold (> 2^W cycles) must not glitch the static leg
        repeat (5000) @(posedge clk);
        measure_period;
        expect_near(hi_cnt[1], 960, 0, "long-hold static Q1");
        expect_near(hi_cnt[2], 960, 0, "long-hold static Q2");
        // ---- BUCKBOOST with short pulses, change dt on the fly
        mode = 2; d1 = 912; d2 = 20; phase = 0; dt = 5;
        repeat (4 * 960) @(posedge clk);
        measure_period;
        expect_near(hi_cnt[1], 912 - 5, 2, "bb Q1 on-time");
        expect_near(hi_cnt[8], 20 - 5, 2, "bb Q8 on-time");
        // ---- BYPASS: legs off, then bypass switch on
        mode = 4;
        repeat (3 * 960) @(posedge clk);
        if (!g_bp) begin errors = errors + 1; $display("ERR bypass switch not on in BYPASS"); end
        if (|g) begin errors = errors + 1; $display("ERR leg gates on in BYPASS"); end
        // ---- back to BUCK from BYPASS (break-before-make handled by monitors)
        mode = 1; d1 = 480; dt = 3;
        repeat (3 * 960) @(posedge clk);
        if (g_bp) begin errors = errors + 1; $display("ERR bypass still on after leaving BYPASS"); end
        // ---- fault: combinational kill + latch
        #3 fault_n = 0;
        #1 if (|g || g_bp || g_in) begin errors = errors + 1; $display("ERR fault did not kill gates"); end
        #50 fault_n = 1;
        repeat (960) @(posedge clk);
        if (|g) begin errors = errors + 1; $display("ERR fault not latched"); end
        // ---- OFF
        rst_n = 0; #50 rst_n = 1; mode = 0;
        repeat (100) @(posedge clk);
        if (|g || g_bp || g_in) begin errors = errors + 1; $display("ERR gates on in OFF"); end
        if (errors == 0) $display("PASS");
        else $display("FAIL %0d", errors);
        $finish;
    end
endmodule

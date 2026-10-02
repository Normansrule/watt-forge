/*
 * wf_ctrl.h -- Watt Forge flagship converter supervisory controller.
 *
 * REFERENCE ONLY -- simulate and review before use. This is not production
 * firmware: it has no hardware abstraction, no watchdog, no calibration and
 * no certification. It exists to document the control logic precisely and is
 * proven equivalent to watt_forge/flagship/control.py by tests/test_control.py.
 *
 * Uses double precision so it matches the Python model bit-for-bit. On a
 * Cortex-M4F (STM32G474) port to float only after re-validating.
 */
#ifndef WF_CTRL_H
#define WF_CTRL_H

enum wf_state { WF_S_INIT = 0, WF_S_PRECHARGE, WF_S_SWEEP, WF_S_TRACK, WF_S_BYPASS, WF_S_FAULT };
enum wf_mode  { WF_M_OFF = 0, WF_M_BUCK, WF_M_BUCKBOOST, WF_M_BOOST, WF_M_BYPASS };

typedef struct {
    double vin, iin, vout, iout, temp;
} wf_meas_t;

typedef struct {
    int state, mode;
    double vin_ref, fs, d1, d2;
} wf_out_t;

typedef struct {
    int state, mode;
    long ticks;
    double voc, vin_ref, p_prev, direction, step;
    int small;
    int sweep_k;
    double sweep_best_p, sweep_best_v, sweep_hi, sweep_lo;
    long since_sweep;
    double p_avg;
    int near;
} wf_ctrl_t;

void wf_ctrl_init(wf_ctrl_t *c);
wf_out_t wf_ctrl_step(wf_ctrl_t *c, const wf_meas_t *m);

#endif

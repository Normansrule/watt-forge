/*
 * wf_ctrl.c -- supervisory state machine, MPPT and mode selection.
 * REFERENCE ONLY -- simulate and review before use. See wf_ctrl.h.
 *
 * Line-for-line port of watt_forge/flagship/control.py. Keep them in sync:
 * tests/test_control.py runs both in closed loop and requires identical output.
 */
#include "wf_ctrl.h"
#include "wf_fs_lut.h"

#define VIN_START 13.0
#define VIN_STOP 11.0
#define VIN_OVP 62.0
#define VIN_MIN_REF 12.0
#define VIN_MAX_REF 60.0
#define VOUT_MIN 38.0
#define VOUT_MAX 59.5
#define VOUT_CV 57.6
#define IIN_OCP 16.0
#define T_OTP 100.0
#define T_OTP_CLR 85.0
#define START_TICKS 1000
#define PRECHARGE_TICKS 50
#define FAULT_RETRY_TICKS 5000
#define SWEEP_STEPS 40
#define RESWEEP_TICKS 300000L
#define BYPASS_BAND 0.02
#define BYPASS_ENTER_TICKS 200
#define BYPASS_CHECK_TICKS 2000
#define BYPASS_MIN_P 20.0
#define M_BUCK_MAX 0.97
#define M_BOOST_MIN 1.03
#define M_HYST 0.01
#define BB_D1 0.95
#define STEP_INIT 0.5
#define STEP_MIN 0.1
#define STEP_MAX 1.0
#define SMALL_DP 0.002
#define BIG_DP 0.02
#define SMALL_COUNT 8

void wf_ctrl_init(wf_ctrl_t *c) {
    c->state = WF_S_INIT; c->mode = WF_M_OFF; c->ticks = 0;
    c->voc = 0.0; c->vin_ref = 0.0; c->p_prev = 0.0; c->direction = -1.0; c->step = STEP_INIT;
    c->small = 0; c->sweep_k = 0; c->sweep_best_p = 0.0; c->sweep_best_v = 0.0;
    c->sweep_hi = 0.0; c->sweep_lo = 0.0; c->since_sweep = 0; c->p_avg = 0.0; c->near = 0;
}

static int is_fault(const wf_meas_t *m) {
    return m->vin > VIN_OVP || m->vout > VOUT_MAX || m->vout < VOUT_MIN || m->iin > IIN_OCP || m->temp > T_OTP;
}

static int is_clear(const wf_meas_t *m) {
    return m->vin <= VIN_OVP && VOUT_MIN + 0.5 <= m->vout && m->vout <= VOUT_MAX - 0.5 &&
           m->iin <= IIN_OCP && m->temp <= T_OTP_CLR;
}

static int select_mode(const wf_ctrl_t *c, const wf_meas_t *m) {
    double ratio = m->vout / c->vin_ref;
    int cur = c->mode;
    if (cur == WF_M_BUCK) return ratio > M_BUCK_MAX + M_HYST ? WF_M_BUCKBOOST : WF_M_BUCK;
    if (cur == WF_M_BOOST) return ratio < M_BOOST_MIN - M_HYST ? WF_M_BUCKBOOST : WF_M_BOOST;
    if (cur == WF_M_BUCKBOOST) {
        if (ratio < M_BUCK_MAX - M_HYST) return WF_M_BUCK;
        if (ratio > M_BOOST_MIN + M_HYST) return WF_M_BOOST;
        return WF_M_BUCKBOOST;
    }
    if (ratio < M_BUCK_MAX) return WF_M_BUCK;
    if (ratio > M_BOOST_MIN) return WF_M_BOOST;
    return WF_M_BUCKBOOST;
}

static double lut_fs(double ratio, double p_frac) {
    int i = 0, j = 0;
    while (i < WF_LUT_NM - 2 && ratio >= WF_LUT_M_EDGES[i + 1]) i++;
    while (j < WF_LUT_NP - 2 && p_frac >= WF_LUT_P_EDGES[j + 1]) j++;
    return WF_LUT_FS[i][j];
}

static void clamp_ref(wf_ctrl_t *c) {
    double hi = VIN_MAX_REF;
    if (c->voc > 0.0 && c->voc < hi) hi = c->voc;
    if (c->vin_ref > hi) c->vin_ref = hi;
    if (c->vin_ref < VIN_MIN_REF) c->vin_ref = VIN_MIN_REF;
}

static void drive(const wf_ctrl_t *c, const wf_meas_t *m, wf_out_t *o) {
    int mode = c->mode;
    double ratio = m->vout / c->vin_ref;
    double p_frac = m->vin * m->iin / WF_LUT_PMAX;
    o->mode = mode;
    o->vin_ref = c->vin_ref;
    if (mode == WF_M_BUCK) { o->d1 = ratio; o->d2 = 0.0; }
    else if (mode == WF_M_BOOST) { o->d1 = 1.0; o->d2 = 1.0 - 1.0 / ratio; }
    else if (mode == WF_M_BUCKBOOST) {
        double d2 = 1.0 - BB_D1 / ratio;
        if (d2 < 0.02) d2 = 0.02;
        o->d1 = BB_D1; o->d2 = d2;
    }
    if (mode == WF_M_BUCK || mode == WF_M_BOOST || mode == WF_M_BUCKBOOST) o->fs = lut_fs(ratio, p_frac);
}

static void start_sweep(wf_ctrl_t *c) {
    double hi, lo;
    c->state = WF_S_SWEEP; c->ticks = 0;
    c->sweep_k = 0; c->sweep_best_p = 0.0; c->sweep_best_v = 0.0;
    hi = 0.95 * c->voc;
    if (hi > VIN_MAX_REF) hi = VIN_MAX_REF;
    lo = 0.45 * c->voc;
    if (lo < VIN_MIN_REF) lo = VIN_MIN_REF;
    c->sweep_hi = hi; c->sweep_lo = lo;
    c->vin_ref = hi;
    c->mode = WF_M_OFF;
}

static void track(wf_ctrl_t *c, const wf_meas_t *m) {
    double p = m->vin * m->iin, dp, mag, scale, dv;
    c->since_sweep++;
    if (m->vout > VOUT_CV) {
        /* constant-voltage limit: back off toward Voc; re-arm the sudden-drop detector */
        c->vin_ref += 0.2;
        clamp_ref(c);
        c->mode = select_mode(c, m);
        c->p_prev = p;
        c->p_avg = p;
        return;
    }
    c->p_avg = 0.99 * c->p_avg + 0.01 * p;
    if (c->since_sweep >= RESWEEP_TICKS || (c->p_avg > 50.0 && p < 0.7 * c->p_avg)) {
        c->voc = c->voc > 0.0 ? c->voc : m->vin;
        start_sweep(c);
        return;
    }
    dp = p - c->p_prev;
    if (dp < 0.0) c->direction = -c->direction;
    mag = dp >= 0.0 ? dp : -dp;
    scale = p > 1.0 ? p : 1.0;
    if (mag < SMALL_DP * scale) {
        c->small++;
        if (c->small >= SMALL_COUNT) {
            c->step = c->step * 0.5;
            if (c->step < STEP_MIN) c->step = STEP_MIN;
            c->small = 0;
        }
    } else {
        c->small = 0;
        if (mag > BIG_DP * scale) {
            c->step = c->step * 2.0;
            if (c->step > STEP_MAX) c->step = STEP_MAX;
        }
    }
    c->vin_ref += c->direction * c->step;
    clamp_ref(c);
    c->p_prev = p;
    c->mode = select_mode(c, m);
    dv = c->vin_ref - m->vout;
    if (dv < 0.0) dv = -dv;
    if (dv < BYPASS_BAND * m->vout && p > BYPASS_MIN_P) c->near++;
    else c->near = 0;
    if (c->near >= BYPASS_ENTER_TICKS) {
        c->state = WF_S_BYPASS; c->ticks = 0; c->near = 0;
        c->mode = WF_M_BYPASS;
        c->vin_ref = m->vout;
    }
}

wf_out_t wf_ctrl_step(wf_ctrl_t *c, const wf_meas_t *m) {
    wf_out_t o = {WF_S_INIT, WF_M_OFF, 0.0, 0.0, 0.0, 0.0};
    c->ticks++;
    if (c->state != WF_S_FAULT && is_fault(m)) { c->state = WF_S_FAULT; c->mode = WF_M_OFF; c->ticks = 0; }
    if (c->state != WF_S_INIT && c->state != WF_S_FAULT && m->vin < VIN_STOP) {
        c->state = WF_S_INIT; c->mode = WF_M_OFF; c->ticks = 0;
    }

    if (c->state == WF_S_FAULT) {
        if (!is_clear(m)) c->ticks = 0;
        else if (c->ticks >= FAULT_RETRY_TICKS) { c->state = WF_S_INIT; c->ticks = 0; }
    } else if (c->state == WF_S_INIT) {
        c->mode = WF_M_OFF;
        if (m->vin < VIN_START) c->ticks = 0;
        else if (c->ticks >= START_TICKS) { c->voc = m->vin; c->state = WF_S_PRECHARGE; c->ticks = 0; }
    } else if (c->state == WF_S_PRECHARGE) {
        if (c->ticks >= PRECHARGE_TICKS) start_sweep(c);
    } else if (c->state == WF_S_SWEEP) {
        if (c->sweep_k > 0) {
            double p = m->vin * m->iin;
            if (p > c->sweep_best_p) { c->sweep_best_p = p; c->sweep_best_v = c->vin_ref; }
        }
        if (c->sweep_k >= SWEEP_STEPS) {
            c->vin_ref = c->sweep_best_p > 0.0 ? c->sweep_best_v : c->sweep_hi;
            c->state = WF_S_TRACK; c->ticks = 0;
            c->p_prev = c->sweep_best_p; c->step = STEP_INIT; c->small = 0; c->near = 0;
            c->p_avg = c->sweep_best_p;
            c->since_sweep = 0;
            c->direction = -1.0;
        } else {
            c->vin_ref = c->sweep_hi - (c->sweep_hi - c->sweep_lo) * c->sweep_k / (SWEEP_STEPS - 1);
            c->sweep_k++;
            c->mode = select_mode(c, m);
            drive(c, m, &o);
        }
    } else if (c->state == WF_S_TRACK) {
        track(c, m);
    } else if (c->state == WF_S_BYPASS) {
        c->mode = WF_M_BYPASS;
        c->vin_ref = m->vout;
        if (c->ticks >= BYPASS_CHECK_TICKS) {
            c->state = WF_S_TRACK; c->ticks = 0;
            c->mode = select_mode(c, m);
            c->p_prev = m->vin * m->iin; c->step = STEP_INIT; c->small = 0; c->near = 0;
            c->direction = -1.0;
        }
    }

    o.state = c->state;
    if (c->state == WF_S_INIT || c->state == WF_S_PRECHARGE || c->state == WF_S_FAULT) {
        o.mode = WF_M_OFF; o.vin_ref = 0.0; o.fs = 0.0; o.d1 = 0.0; o.d2 = 0.0;
    } else if (c->state == WF_S_BYPASS) {
        o.mode = WF_M_BYPASS; o.vin_ref = c->vin_ref; o.fs = 0.0; o.d1 = 1.0; o.d2 = 0.0;
    } else if (c->state == WF_S_TRACK) {
        drive(c, m, &o);
    }
    return o;
}

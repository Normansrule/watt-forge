/*
 * wf_mppt.h -- Watt Forge MPPT algorithm library and online efficiency optimiser.
 *
 * REFERENCE ONLY -- simulate and review before use. Not production firmware.
 * C port of watt_forge/control/mppt.py and efficiency.py::HillClimb. tests/test_control_lib.py
 * replays the Python trackers' measurements into this code and requires identical decisions.
 *
 * All trackers command a panel-voltage reference. Call wf_mppt_update() once per update period
 * with the averaged panel voltage and current; read t->vref; honour t->open_request (one
 * open-circuit sample) for the fractional-Voc tracker.
 *
 * Double precision, to match the Python model bit for bit. Re-validate before porting to float.
 */
#ifndef WF_MPPT_H
#define WF_MPPT_H

#include <stdint.h>

typedef enum {
    WF_PO = 0, WF_VSPO, WF_INC, WF_VSINC, WF_FOCV, WF_ESC, WF_PSO, WF_SCAN, WF_MPPT_COUNT
} wf_mppt_kind;

#define WF_PSO_MAX 8

typedef struct {
    /* parameters (wf_mppt_defaults fills them; override before wf_mppt_reset) */
    double step, gain, step_min, step_max, tol;          /* hill climbing */
    double k; int every;                                  /* fractional Voc */
    double amp, hp;                                       /* extremum seeking (gain shared) */
    int n; double w, c1, c2, restart;                     /* particle swarm */
    int points; double lo_frac, drop; int rescan;         /* global scan */
    int period;                                           /* plant ticks per update */
} wf_mppt_params;

typedef struct wf_mppt {
    wf_mppt_kind kind;
    wf_mppt_params p;
    double vref, voc;
    int open_request;
    /* hill climbing / shared */
    double p_prev, v_prev, i_prev, direction, cur_step;
    int first;
    /* fractional Voc */
    int count, sampling;
    /* extremum seeking */
    double vhat, hpf; int ks;
    /* particle swarm */
    uint32_t rng;
    double x[WF_PSO_MAX], vel[WF_PSO_MAX], pbest[WF_PSO_MAX], xbest[WF_PSO_MAX];
    double gbest_p, gbest_x, p_track;
    int j, iters, searching;
    /* global scan */
    int scanning, sk, since;
    double best_p, best_v, top, bottom, p_avg;
    /* local variable-step P&O used by PSO and SCAN after their global search */
    double l_vref, l_p_prev, l_v_prev, l_dir, l_step;
} wf_mppt;

void wf_mppt_defaults(wf_mppt_kind kind, wf_mppt_params *p);
void wf_mppt_init(wf_mppt *t, wf_mppt_kind kind, const wf_mppt_params *p, uint32_t seed);
void wf_mppt_reset(wf_mppt *t, double voc);
void wf_mppt_update(wf_mppt *t, double v, double i);

/* Online optimiser: discrete extremum seeking over n ordered settings (frequencies, dead times). */
typedef struct {
    int n, idx, probe, direction, fails, resting, rest;
    double margin, base_cost;
} wf_hillclimb;

void wf_hillclimb_init(wf_hillclimb *h, int n, int start, double margin, int rest);
int wf_hillclimb_update(wf_hillclimb *h, double cost);

/* xorshift32, identical to watt_forge/control/rng.py */
uint32_t wf_xorshift32(uint32_t *state);

#endif

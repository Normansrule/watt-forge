/*
 * wf_mppt.c -- see wf_mppt.h. REFERENCE ONLY -- simulate and review before use.
 * Mirrors watt_forge/control/mppt.py statement for statement.
 */
#include "wf_mppt.h"

#define V_MIN 12.0
#define V_MAX 60.0

static const double SIN10[10] = {
    0.0, 0.5877852522924731, 0.9510565162951535, 0.9510565162951536, 0.5877852522924732,
    1.2246467991473532e-16, -0.587785252292473, -0.9510565162951535, -0.9510565162951536,
    -0.5877852522924734 };

static double clampd(double x, double lo, double hi) { return x < lo ? lo : (x > hi ? hi : x); }

uint32_t wf_xorshift32(uint32_t *s)
{
    uint32_t x = *s;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *s = x;
    return x;
}

static double uniform(uint32_t *s) { return (double)wf_xorshift32(s) / 4294967296.0; }

static double hi_lim(const wf_mppt *t)
{
    double h = 0.98 * t->voc;
    return h < V_MAX ? h : V_MAX;
}

void wf_mppt_defaults(wf_mppt_kind kind, wf_mppt_params *p)
{
    /* zero everything, then the per-algorithm defaults: the tuned values in data/mppt_tuned.json */
    wf_mppt_params z = {0};
    *p = z;
    p->period = 2;
    switch (kind) {
    case WF_PO:    p->step = 0.2; p->period = 1; break;
    case WF_VSPO:  p->gain = 0.04; p->step_min = 0.3; p->step_max = 2.0; break;
    case WF_INC:   p->step = 0.3; p->tol = 0.001; break;
    case WF_VSINC: p->gain = 0.08; p->step_min = 0.3; p->step_max = 2.0; p->tol = 0.03; p->step = 0.5; break;
    case WF_FOCV:  p->k = 0.84; p->every = 1000; p->period = 1; break;
    case WF_ESC:   p->amp = 0.8; p->gain = 0.016; p->hp = 0.8; p->period = 1; break;
    case WF_PSO:   p->n = 4; p->w = 0.4; p->c1 = 1.0; p->c2 = 1.6; p->restart = 0.25; break;
    case WF_SCAN:  p->points = 8; p->lo_frac = 0.25; p->rescan = 1500; p->drop = 0.45; break;
    default: break;
    }
}

void wf_mppt_init(wf_mppt *t, wf_mppt_kind kind, const wf_mppt_params *p, uint32_t seed)
{
    wf_mppt z = {0};
    *t = z;
    t->kind = kind;
    if (p) t->p = *p; else wf_mppt_defaults(kind, &t->p);
    t->rng = seed ? seed : 2463534242u;
}

/* ---- local variable-step P&O (VSPO defaults), used after a global search */
static void local_reset(wf_mppt *t, double vref)
{
    t->l_p_prev = -1.0; t->l_v_prev = 0.0; t->l_dir = -1.0; t->l_step = 0.5; t->l_vref = vref;
}

static void local_update(wf_mppt *t, double v, double i)
{
    double p = v * i;
    if (t->l_p_prev >= 0.0) {
        double dv = v - t->l_v_prev, dp = p - t->l_p_prev;
        if (dp < 0.0) t->l_dir = -t->l_dir;
        if (dv > 0.05 || dv < -0.05) {
            double slope = dp / dv;
            if (slope < 0.0) slope = -slope;
            t->l_step = clampd(0.04 * slope, 0.3, 2.0);   /* VSPO defaults */
        }
    }
    t->l_p_prev = p; t->l_v_prev = v;
    t->l_vref = clampd(t->l_vref + t->l_dir * t->l_step, V_MIN, hi_lim(t));
}

static void pso_spread(wf_mppt *t)
{
    double lo = V_MIN, hi = hi_lim(t);
    int j;
    for (j = 0; j < t->p.n; j++) {
        t->x[j] = lo + (hi - lo) * (j + 0.5) / t->p.n;
        t->vel[j] = 0.0; t->pbest[j] = -1.0; t->xbest[j] = t->x[j];
    }
    t->gbest_p = -1.0; t->gbest_x = t->x[0]; t->j = 0; t->iters = 0; t->searching = 1; t->vref = t->x[0];
}

static void scan_start(wf_mppt *t)
{
    double lo = t->p.lo_frac * t->voc;
    t->scanning = 1; t->sk = 0; t->best_p = -1.0; t->best_v = 0.0; t->top = hi_lim(t);
    t->bottom = lo > V_MIN ? lo : V_MIN;
    t->vref = t->top; t->since = 0;
}

void wf_mppt_reset(wf_mppt *t, double voc)
{
    t->voc = voc;
    t->vref = clampd(0.8 * voc, V_MIN, hi_lim(t));
    t->open_request = 0;
    switch (t->kind) {
    case WF_PO: t->p_prev = -1.0; t->direction = -1.0; break;
    case WF_VSPO: t->p_prev = -1.0; t->v_prev = 0.0; t->direction = -1.0; t->cur_step = 0.5; break;
    case WF_INC: case WF_VSINC:
        t->first = 1; t->v_prev = 0.0; t->i_prev = 0.0; t->vref = t->vref - t->p.step; break;
    case WF_FOCV: t->count = 0; t->vref = clampd(t->p.k * voc, V_MIN, hi_lim(t)); t->sampling = 0; break;
    case WF_ESC: t->vhat = t->vref; t->ks = 0; t->p_prev = -1.0; t->hpf = 0.0; break;
    case WF_PSO: pso_spread(t); t->p_track = 0.0; break;
    case WF_SCAN: t->p_avg = 0.0; scan_start(t); break;
    default: break;
    }
}

static double inc_direction(const wf_mppt *t, double v, double i)
{
    double dv = v - t->v_prev, di = i - t->i_prev;
    double g = v > 1.0 ? i / v : 0.0;
    double e;
    if (dv > -0.05 && dv < 0.05) {
        if (di > -0.02 && di < 0.02) return 0.0;
        return di > 0.0 ? 1.0 : -1.0;
    }
    e = di / dv + g;
    if (e > -t->p.tol * g && e < t->p.tol * g) return 0.0;
    return e > 0.0 ? 1.0 : -1.0;
}

static double vsinc_step(const wf_mppt *t, double v, double i)
{
    double dv = v - t->v_prev, slope;
    if (dv > -0.05 && dv < 0.05) return t->p.step_min;
    slope = (v * i - t->v_prev * t->i_prev) / dv;
    if (slope < 0.0) slope = -slope;
    return clampd(t->p.gain * slope, t->p.step_min, t->p.step_max);
}

void wf_mppt_update(wf_mppt *t, double v, double i)
{
    double p = v * i;
    switch (t->kind) {
    case WF_PO:
        if (t->p_prev >= 0.0 && p < t->p_prev) t->direction = -t->direction;
        t->p_prev = p;
        t->vref = clampd(t->vref + t->direction * t->p.step, V_MIN, hi_lim(t));
        break;
    case WF_VSPO:
        if (t->p_prev >= 0.0) {
            double dv = v - t->v_prev, dp = p - t->p_prev;
            if (dp < 0.0) t->direction = -t->direction;
            if (dv > 0.05 || dv < -0.05) {
                double slope = dp / dv;
                if (slope < 0.0) slope = -slope;
                t->cur_step = clampd(t->p.gain * slope, t->p.step_min, t->p.step_max);
            }
        }
        t->p_prev = p; t->v_prev = v;
        t->vref = clampd(t->vref + t->direction * t->cur_step, V_MIN, hi_lim(t));
        break;
    case WF_INC:
    case WF_VSINC:
        if (!t->first) {
            double d = inc_direction(t, v, i);
            double s = t->kind == WF_INC ? t->p.step : vsinc_step(t, v, i);
            t->vref = clampd(t->vref + d * s, V_MIN, hi_lim(t));
        }
        t->first = 0;
        t->v_prev = v; t->i_prev = i;
        break;
    case WF_FOCV:
        if (t->sampling) {
            t->sampling = 0; t->open_request = 0; t->voc = v;
            t->vref = clampd(t->p.k * v, V_MIN, hi_lim(t));
            break;
        }
        t->count += 1;
        if (t->count >= t->p.every) { t->count = 0; t->sampling = 1; t->open_request = 1; }
        break;
    case WF_ESC:
        if (t->p_prev >= 0.0) t->hpf = t->p.hp * (t->hpf + p - t->p_prev);
        t->p_prev = p;
        t->vhat = clampd(t->vhat + t->p.gain * t->hpf * SIN10[t->ks], V_MIN, hi_lim(t));
        t->ks = (t->ks + 1) % 10;
        t->vref = clampd(t->vhat + t->p.amp * SIN10[t->ks], V_MIN, hi_lim(t));
        break;
    case WF_PSO:
        if (t->searching) {
            if (p > t->pbest[t->j]) { t->pbest[t->j] = p; t->xbest[t->j] = t->x[t->j]; }
            if (p > t->gbest_p) { t->gbest_p = p; t->gbest_x = t->x[t->j]; }
            t->j += 1;
            if (t->j >= t->p.n) {
                double spread = 0.0, lo = V_MIN, hi = hi_lim(t);
                int k;
                t->j = 0; t->iters += 1;
                for (k = 0; k < t->p.n; k++) {
                    double r1 = uniform(&t->rng), r2 = uniform(&t->rng), d;
                    t->vel[k] = t->p.w * t->vel[k] + t->p.c1 * r1 * (t->xbest[k] - t->x[k])
                              + t->p.c2 * r2 * (t->gbest_x - t->x[k]);
                    t->x[k] = clampd(t->x[k] + t->vel[k], lo, hi);
                    d = t->x[k] - t->gbest_x;
                    if (d < 0.0) d = -d;
                    if (d > spread) spread = d;
                }
                if (spread < 0.5 || t->iters >= 15) {
                    t->searching = 0;
                    local_reset(t, t->gbest_x);
                    t->vref = t->gbest_x; t->p_track = t->gbest_p;
                    break;
                }
            }
            t->vref = t->x[t->j];
            break;
        }
        if (t->p_track > 1.0) {
            double ratio = p / t->p_track;
            if (ratio < 1.0 - t->p.restart || ratio > 1.0 + t->p.restart) { pso_spread(t); break; }
        }
        t->p_track = 0.98 * t->p_track + 0.02 * p;
        local_update(t, v, i);
        t->vref = t->l_vref;
        break;
    case WF_SCAN:
        if (t->scanning) {
            if (p > t->best_p) { t->best_p = p; t->best_v = t->vref; }
            t->sk += 1;
            if (t->sk >= t->p.points) {
                t->scanning = 0;
                local_reset(t, t->best_v);
                t->vref = t->best_v; t->p_avg = t->best_p;
                break;
            }
            t->vref = t->top - (t->top - t->bottom) * t->sk / (t->p.points - 1);
            break;
        }
        t->since += 1;
        if (t->since >= t->p.rescan || (t->p_avg > 20.0 && p < t->p.drop * t->p_avg)) { scan_start(t); break; }
        t->p_avg = 0.97 * t->p_avg + 0.03 * p;
        local_update(t, v, i);
        t->vref = t->l_vref;
        break;
    default:
        break;
    }
}

/* ---- online optimiser */
void wf_hillclimb_init(wf_hillclimb *h, int n, int start, double margin, int rest)
{
    h->n = n; h->idx = start; h->margin = margin; h->rest = rest;
    h->base_cost = -1.0; h->probe = 0; h->direction = 1; h->fails = 0; h->resting = 0;
}

int wf_hillclimb_update(wf_hillclimb *h, double cost)
{
    if (h->resting > 0) {
        h->resting -= 1;
        if (h->resting == 0) h->base_cost = -1.0;
        return h->idx;
    }
    if (h->probe == 0) {
        int nxt;
        h->base_cost = cost;
        nxt = h->idx + h->direction;
        if (nxt < 0 || nxt >= h->n) {
            h->direction = -h->direction;
            nxt = h->idx + h->direction;
        }
        h->probe = h->direction;
        h->idx = nxt;
        return h->idx;
    }
    if (cost < h->base_cost - h->margin) {
        h->base_cost = cost; h->fails = 0; h->probe = 0;
        return h->idx;
    }
    h->idx -= h->probe;
    h->probe = 0;
    h->direction = -h->direction;
    h->fails += 1;
    if (h->fails >= 2) { h->fails = 0; h->resting = h->rest; }
    return h->idx;
}

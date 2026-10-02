/*
 * wf_harness.c -- host test harness for the reference controller.
 * Reads "vin iin vout iout temp" per line on stdin, prints
 * "state mode vin_ref fs d1 d2" per line on stdout (flushed each tick so a
 * closed-loop plant model can drive it through pipes).
 */
#include <stdio.h>
#include "wf_ctrl.h"

int main(void) {
    wf_ctrl_t c;
    wf_meas_t m;
    wf_ctrl_init(&c);
    while (scanf("%lf %lf %lf %lf %lf", &m.vin, &m.iin, &m.vout, &m.iout, &m.temp) == 5) {
        wf_out_t o = wf_ctrl_step(&c, &m);
        printf("%d %d %.6f %.1f %.6f %.6f\n", o.state, o.mode, o.vin_ref, o.fs, o.d1, o.d2);
        fflush(stdout);
    }
    return 0;
}

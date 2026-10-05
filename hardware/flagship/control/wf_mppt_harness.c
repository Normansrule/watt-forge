/*
 * wf_mppt_harness.c -- test harness for wf_mppt.c (used by tests/test_control_lib.py).
 *   wf_mppt_harness mppt <kind 0-7> <seed> [name=value ...]
 *       stdin: "R <voc>" resets, "U <v> <i>" updates; stdout: "<vref %.17g> <open_request>"
 *   wf_mppt_harness hc <n> <start> <margin> <rest>
 *       stdin: one cost per line; stdout: the index to apply next
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "wf_mppt.h"

static void set_param(wf_mppt_params *p, const char *kv)
{
    char name[32];
    const char *eq = strchr(kv, '=');
    double val;
    size_t n;
    if (!eq) return;
    n = (size_t)(eq - kv);
    if (n >= sizeof name) return;
    memcpy(name, kv, n); name[n] = 0;
    val = atof(eq + 1);
#define D(f) if (!strcmp(name, #f)) { p->f = val; return; }
#define I(f) if (!strcmp(name, #f)) { p->f = (int)val; return; }
    D(step) D(gain) D(step_min) D(step_max) D(tol) D(k) I(every) D(amp) D(hp)
    I(n) D(w) D(c1) D(c2) D(restart) I(points) D(lo_frac) D(drop) I(rescan) I(period)
#undef D
#undef I
    fprintf(stderr, "unknown parameter %s\n", name);
    exit(2);
}

int main(int argc, char **argv)
{
    char line[256];
    if (argc >= 4 && !strcmp(argv[1], "mppt")) {
        wf_mppt t;
        wf_mppt_params p;
        wf_mppt_kind kind = (wf_mppt_kind)atoi(argv[2]);
        int a;
        wf_mppt_defaults(kind, &p);
        for (a = 4; a < argc; a++) set_param(&p, argv[a]);
        wf_mppt_init(&t, kind, &p, (uint32_t)strtoul(argv[3], NULL, 10));
        while (fgets(line, sizeof line, stdin)) {
            double x, y;
            if (line[0] == 'R' && sscanf(line + 1, "%lf", &x) == 1) wf_mppt_reset(&t, x);
            else if (line[0] == 'U' && sscanf(line + 1, "%lf %lf", &x, &y) == 2) wf_mppt_update(&t, x, y);
            else continue;
            printf("%.17g %d\n", t.vref, t.open_request);
        }
        return 0;
    }
    if (argc == 6 && !strcmp(argv[1], "hc")) {
        wf_hillclimb h;
        wf_hillclimb_init(&h, atoi(argv[2]), atoi(argv[3]), atof(argv[4]), atoi(argv[5]));
        while (fgets(line, sizeof line, stdin)) {
            double c;
            if (sscanf(line, "%lf", &c) == 1) printf("%d\n", wf_hillclimb_update(&h, c));
        }
        return 0;
    }
    fprintf(stderr, "usage: wf_mppt_harness mppt <kind> <seed> [k=v...] | hc <n> <start> <margin> <rest>\n");
    return 2;
}

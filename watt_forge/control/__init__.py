"""Control-algorithm library: maximum power point tracking (MPPT) and converter-efficiency controls.

    rng         deterministic noise shared bit-for-bit with the JavaScript and C ports
    profiles    irradiance/temperature test profiles (EN 50530-style ramps, clouds, shading, ...)
    plant       PV panel + input-voltage loop + sensors (noise, ADC quantisation)
    mppt        eight MPPT algorithms behind one interface
    bench       closed-loop runner and metrics (dynamic MPPT efficiency, energy to battery)
    efficiency  adaptive switching frequency, adaptive dead time, burst mode, bypass, daily energy

REFERENCE ONLY: simulate and review before use. Nothing here is production firmware.
"""

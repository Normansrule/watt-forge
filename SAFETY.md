# Safety

**Watt Forge is a design and simulation reference, not a build-and-energize guide.** Nothing in this repository replaces training, supervision and proper lab practice. Any physical build is at your own risk.

- **A solar panel cannot be switched off.** In daylight its terminals are live (up to ~50 V for one 72-cell panel, far more in a string).
- **Batteries deliver enormous fault currents.** A 48 V lithium pack can deliver hundreds to thousands of amperes into a short. Fuse the battery connection, close to the battery.
- **Capacitors stay charged** after power is removed. Measure before touching.
- **Three-level (flying-capacitor) stages have a start-up hazard.** Until the flying capacitors are precharged to half the bus, a single switch can see the full input voltage. Bring a new board up slowly, from a current-limited bench supply, with the precharge verified on an oscilloscope, before a panel or battery is ever connected.
- **GaN gates are fragile.** Overshoot above the gate's absolute maximum (6 V for the EPC parts used here) destroys the device, and a destroyed switch can fail short.
- **The control code is a reference.** `hardware/flagship/control/*.c` and `hardware/flagship/hdl/*.v` are labelled *reference, simulate and review before use*. They have no watchdog, calibration or certification and are not production firmware.

# Flagship design rationale: hybrid three-level GaN buck-boost for solar

> **Reference design, not a build guide.** Everything here is a design and simulation reference. A physical build is at your own risk and needs proper high-voltage and stored-energy safety practice (see [SAFETY.md](../../SAFETY.md)). The control code is labelled *reference: simulate and review before use*.

## 1. The job

| Item | Value |
|---|---|
| Input | one photovoltaic (PV) panel, 12-60 V operating, open-circuit voltage (Voc) up to 60 V |
| Output | 48 V-nominal battery bus, 40-58 V |
| Power | 400 W, derated below ~27 V by a 15 A input-current limit (175 W at 12 V) |
| Must do | maximum power point tracking (MPPT), step up **and** down, survive partial shading, reverse polarity and night-time backfeed |
| Goal | highest peak and solar-weighted efficiency the physics allows, with every loss accounted for |

A 48 V battery with a panel whose maximum power point (MPP) wanders from roughly 18 V (hot, shaded, or a 36-cell module) to 50+ V (cold 96-cell module) means the converter spends real time on **both sides of unity ratio**. That rules out a plain buck or boost and makes the buck-boost family the natural starting point.

## 2. Topology: why "three-level flying-capacitor four-switch buck-boost"

Start from the non-inverting four-switch buck-boost (input half-bridge, inductor, output half-bridge). It is the standard answer because in buck mode the output leg just sits "on", in boost mode the input leg sits "on", and only near unity do both legs switch.

Then replace each two-level half-bridge with a **three-level flying-capacitor leg** (four switches and one flying capacitor, CF). Three things happen:

1. **Each switch blocks half the bus.** Steady state is at most 30 V across a device, so the switching-loss terms (which scale roughly with V x Qoss) shrink about 2-4x at the same device size.
2. **The switch node steps at twice the switching frequency in half-size steps**, so for the same inductor the current ripple falls by up to 4x. We spend that as a smaller inductor, a lower switching frequency, or both. The optimizer picked the lower frequency (50-125 kHz) because it maximizes efficiency.
3. **At D = 0.5 the leg is a switched-capacitor (SC) converter.** When Vout = 2 Vin (boost side) the node voltage sits at Vout/2 almost continuously. The inductor current barely ripples (0.13 A peak-to-peak at 24 V -> 48 V, 300 W), and the inductor simply *soft-charges* the flying capacitor. That is the classic 2:1 series-parallel SC converter without its intrinsic charge-sharing loss (Seeman & Sanders 2008; Lei & Pilawa-Podgurski 2015).

That third point is the "hybrid": capacitors do the voltage division and store energy far more densely than inductors, while the small inductor makes the charge transfer lossless. The same structure covers buck, boost and the SC point without changing hardware.

**Being honest about the SC region.** At 24 V in, 300 W still means 12.5 A of input current. Conduction loss scales with I^2, so the SC point is *not* the most efficient operating point in absolute terms (98.7 % there vs 99.3 % at 36 V). Its win is the near-zero ripple: almost no inductor AC or core loss, and room to shrink the magnetics. With near-zero ripple there is also no negative current to buy zero-voltage switching (ZVS), so its edges are hard-switched.

## 3. Devices: why GaN, why EPC2361, why 100 V

* **Gallium nitride (GaN) vs silicon (Si) vs silicon carbide (SiC)** in the *same* converter at 150 kHz (36 V -> 48 V, 300 W; `docs/img/device_compare.png`):

  | Device | Total loss | Efficiency |
  |---|---|---|
  | EPC2361 (GaN) | 2.5 W | 99.17 % |
  | ISC030N10NM6 (Si) | 4.2 W | 98.62 % |
  | CSD19536KTT (Si) | 7.1 W | 97.69 % |
  | IMT65R010M2H (SiC) | 9.3 W | 96.99 % |
  | C3M0015065K (SiC) | 15.3 W | 95.14 % |

  GaN wins on the terms that matter here: Qrr = 0 (no body diode), about a fifth of the gate charge, and roughly half the output charge of a silicon MOSFET with the same on-resistance. SiC is a 650 V+ technology. At 30 V it pays for voltage it never uses with 10x the on-resistance, so it is shown to make the point, not as a contender.
* **Among six 100 V EPC parts** the loss model's CEC-weighted sweep picked **EPC2361** (99.06 % averaged over 24/36/56 V), ahead of EPC2302 (98.97 %) and EPC2071 (98.95 %). The lowest on-resistance wins because the three-level legs already cut the voltage-dependent switching loss.
* **Why 100 V parts for a 30 V job?** During precharge, before a flying capacitor reaches Vbus/2, a single switch can see the whole 60 V bus. A 40 V part (EPC2067) has no margin; 80 V (EPC2218A) would work; 100 V gives margin for ringing and a panel's cold-morning Voc.

## 4. Bidirectional GaN switches: where they earn their place

A monolithic bidirectional switch (BDS) blocks voltage in both directions with one channel. We use **Innoscience INV100FQ030C** (100 V, 3.2 mOhm max) twice:

* **Q_IN, the input disconnect.** It blocks reverse polarity and stops the battery back-feeding the panel at night. The usual solution is two back-to-back MOSFETs (two channels in series); one BDS halves the part count and the conduction path.
* **Q_BP, the pass-through bypass.** When the panel's MPP sits within 2 % of the battery voltage, switching stops and the panel is tied to the battery. That is 99.73 % in the model at 48 V, 400 W, against 99.22-99.45 % switching nearby, and it removes the both-legs-switching dip at Vin = Vout. MPPT is lost while bypassed, so the controller re-checks every 2 s.

The cost is visible in the loss budget: Q_IN is 0.2-0.9 W depending on input current. Paralleling two BDS parts would halve that if the budget allows. The CoBB work (Aron et al. 2025) shows the more radical use: BDS inside the switching cells to shrink passives about 3x. That is a natural next step for a density-optimized variant.

## 5. Passives

| Part | Choice | Why |
|---|---|---|
| Inductor | Coilcraft SER2918H-472, 4.7 uH, 2.86 mOhm max DCR, 59 A Isat | lowest DCR in class; with three-level ripple the core runs at a few mT, so copper dominates |
| Flying caps | 4x TDK C5750X7S2A106K230KB (10 uF, 100 V, X7S) per leg | X7S keeps ~60 % of capacitance at 30 V bias (~24 uF effective); ripple stays <= 10 % of Vbus/2 in every operating point (checked) |
| Input/output | 6x same MLCC + 2x 33 uF electrolytic each side | MLCCs carry ripple, electrolytics give MPPT loop and surge energy |
| Shunts | 2x Bourns CSS2H-3920R-1L00F (1 mOhm) | panel current (MPPT) and battery current (charge control) |

## 6. Control

The supervisory controller is a 1 kHz state machine (`docs/img/state_machine.svg`):

* **INIT** waits for Vin > 13 V for 1 s and records Voc.
* **PRECHARGE** brings the flying capacitors to Vbus/2.
* **SWEEP** runs a 40-step global scan, so partial shading can't strand it on a local maximum.
* **TRACK** runs perturb-and-observe (P&O) with an adaptive step, plus a constant-voltage battery limit.
* **BYPASS** is entered when the MPP is within 2 % of Vbat.
* **FAULT** latches and retries after 5 s.

Mode selection uses M = Vout/Vref with 1 % hysteresis. Switching frequency comes from a lookup table the loss model generates (`data/fs_lut.json`, compiled into `wf_fs_lut.h`).

* `hardware/flagship/control/wf_ctrl.c` and `watt_forge/flagship/control.py` are **proven identical** in closed loop with the PV model (6,200 ticks, zero mismatches; `tests/test_control.py`).
* The MPPT holds more than 99.5 % of the available power in steady sun, finds the global maximum under partial shading, and enters bypass when it should.
* `hardware/flagship/hdl/wf_pwm3l.v` is the three-level modulator: phase-shifted carriers, dead-time insertion, bypass break-before-make, and a latched fault kill. Its self-checking testbench checks shoot-through, dead time, duty, phase, bypass sequencing and the fault latch. The testbench caught a real counter-saturation bug during development.

## 7. Predicted performance (model; not a measurement)

| Operating point | Mode | f | Loss | Efficiency |
|---|---|---|---|---|
| 56 V -> 48 V, 400 W | buck | 75 kHz | 2.21 W | **99.45 %** |
| 36 V -> 48 V, 300 W | boost | 75 kHz | 2.23 W | 99.26 % |
| 24 V -> 48 V, 300 W | boost, SC 1:2 | 100 kHz | 3.82 W | 98.74 % |
| 12 V -> 48 V, 175 W | boost | 75 kHz | 4.69 W | 97.39 % |
| 48 V, 400 W | bypass | - | 1.07 W | 99.73 % |

These efficiencies include 0.55 W of housekeeping. The CEC-weighted efficiency is 97.5 % at 12 V, 98.8 % at 24 V, 99.1 % at 36 V and 99.25 % at 56 V (full curve in `data/flagship_results.json`).

**Where the physics says no:**

* At 12 V the converter carries 15 A through four series switches, the inductor and the disconnect. Conduction loss scales with I^2, so it tops out near 97.4 %.
* At 10 % load the fixed 0.55 W of housekeeping alone costs 1-3 points.

**How much to trust the numbers:**

* **Two independent calculations agree.** The time-domain circuit simulation reproduces the analytic model to within 0.15 points everywhere tested (10 points spanning all modes and loads). ngspice reproduces the circuit simulation to 5e-5 (`tests/test_flagship_sim.py`).
* **Published hardware sets the ceiling.** The best measured GaN buck-boost results we could verify are 99.0 % (TI TIDA-010949, 600 W, control power excluded) and 99.3 % (Heydari et al., APEC 2023, conditions only partly verified). Treat anything this model says above ~99.3 % as a claim that needs hardware.
* **Known unmodelled effects:**
  * PCB AC resistance and layout parasitics beyond one commutation-loop estimate
  * thermal coupling
  * GaN dynamic on-resistance, beyond a flat 10 % allowance
  * Coss hysteresis, beyond a 10 % estimate
  * current-sense and ADC error in the MPPT
  * gate-driver quiescent spread

  Expect several tenths of a point less in hardware.

## 8. What to do next (if you build it)

1. Lay out the commutation loops first (each three-level leg has two). Measure the loop inductance and put it into `Params.l_loop`.
2. Replace every ESTIMATE in `watt_forge/flagship/params.py` with bench data, starting with thermal and dynamic on-resistance.
3. Validate the core loss with the inductor maker's calculator.
4. Bring up at low voltage with a current-limited supply, flying-capacitor precharge verified on a scope, before a panel ever touches it.

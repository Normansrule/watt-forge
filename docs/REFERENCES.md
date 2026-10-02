# References and verified figures

_Last verified: 2026-09-30. Generated from `data/references.json` by `scripts/make_web_data.py`; edit the JSON, not this file._

**Rule used everywhere in this repo:** every efficiency figure is quoted with its exact test conditions (input, output, power) and what it includes. A best-case lab number is never presented as typical. Research-stage results are labelled as such.

## Corrections to commonly quoted numbers

- The MDPI *Sustainability* 2024 hybrid SC buck-boost paper's 96 % / 99.2 % are **PV energy-harvest ratios**, not converter efficiency.
- A "96-97 % switched-capacitor buck-boost for PV" could **not** be verified; the closest verified paper (Liang et al., APEC 2012) reports 92.5 %.
- The CoBB (monolithic bidirectional GaN buck-boost) results are from **MIT** (Aron, Eliat-Eliat, Buonato, Coday) and **exclude gate-drive loss**.
- The TI GaN optimizer's 99.5-99.6 % is a **pass-through** state; its switching peak is 99.0 %.
- The piezoelectric ">99 %" figure (Boles et al. 2021) appears to be **calculated**, not measured.

## Textbook

### Fundamentals of Power Electronics, 3rd ed.

- **Authors:** R. W. Erickson, D. Maksimovic (2020). **Venue:** Springer.
- **Link:** [10.1007/978-3-030-43881-4](https://doi.org/10.1007/978-3-030-43881-4) (also https://link.springer.com/book/10.1007/978-3-030-43881-4)
- **In plain language:** The standard text for conversion ratios, volt-second and charge balance, CCM/DCM boundaries and averaged loss models used throughout the lessons.
- **Verification:** VERIFIED (publisher page)

## Magnetics

### Accurate prediction of ferrite core loss with nonsinusoidal waveforms using only Steinmetz parameters

- **Authors:** K. Venkatachalam, C. R. Sullivan, T. Abdallah, H. Tacca (2002). **Venue:** IEEE COMPEL.
- **Link:** [10.1109/CIPE.2002.1196712](https://doi.org/10.1109/CIPE.2002.1196712)
- **In plain language:** The improved Generalized Steinmetz Equation (iGSE) used for all inductor core-loss estimates here.
- **Verification:** VERIFIED (OpenAlex, DOI redirect)

## Switched capacitor

### Analysis and Optimization of Switched-Capacitor DC-DC Converters

- **Authors:** M. D. Seeman, S. R. Sanders (2008). **Venue:** IEEE Trans. Power Electronics 23(2):841-851.
- **Link:** [10.1109/TPEL.2007.915182](https://doi.org/10.1109/TPEL.2007.915182)
- **In plain language:** Canonical slow-switching / fast-switching limit (SSL/FSL) output-resistance analysis of switched-capacitor converters.
- **Verification:** VERIFIED (Berkeley publication list, DOI redirect)

### A General Method for Analyzing Resonant and Soft-Charging Operation of Switched-Capacitor Converters

- **Authors:** Y. Lei, R. C. N. Pilawa-Podgurski (2015). **Venue:** IEEE Trans. Power Electronics 30(10):5650-5664.
- **Link:** [10.1109/TPEL.2014.2377738](https://doi.org/10.1109/TPEL.2014.2377738)
- **In plain language:** Shows when adding a single inductor removes the charge-sharing loss (soft charging), the principle behind the flagship's SC region.
- **Verification:** VERIFIED (Illinois Experts, DOI redirect)

## Devices

### Review of Commercial GaN Power Devices and GaN-Based Converter Design Challenges

- **Authors:** E. A. Jones, F. Wang, D. Costinett (2016). **Venue:** IEEE J. Emerging and Selected Topics in Power Electronics 4(3):707-719.
- **Link:** [10.1109/JESTPE.2016.2582685](https://doi.org/10.1109/JESTPE.2016.2582685)
- **In plain language:** Survey of commercial GaN transistors and practical design issues (layout parasitics, gate drive, dynamic on-resistance, thermal).
- **Verification:** VERIFIED (bibliographic)

## Hybrid SC for PV

### Switched-Capacitor-Based Hybrid Resonant Bidirectional Buck-Boost Converter for Improving Energy Harvesting in Photovoltaic Systems

- **Authors:** C. M. A. da Luz, K. F. A. Okada, A. S. Morais, F. L. Tofoli, E. R. Ribeiro (2024). **Venue:** MDPI Sustainability 16(22):10142.
- **Link:** [10.3390/su162210142](https://doi.org/10.3390/su162210142) (also https://www.mdpi.com/2071-1050/16/22/10142)
- **Headline figure:** 96 % and 99.2 % (NOT converter efficiency)
- **Exact conditions:** Figures are extracted PV power divided by the string's theoretical maximum (energy harvest). Scenario 1: 38.4 W -> 57.6 W; scenario 2: 36 W -> 49.6 W; 1050 W/m^2, 45 C, four-module string of 20 W and 10 W modules, variable-resistor load, 50 kHz, Infineon IPP082N10NF2 MOSFETs. No standalone converter efficiency is reported.
- **In plain language:** A differential-power-processing converter shuffles power between mismatched PV modules so the string recovers most of its available power.
- **Verification:** VERIFIED (publisher page and full text)

### High efficiency switched capacitor buck-boost converter for PV application

- **Authors:** Z. Liang, A. Q. Huang, R. Guo (2012). **Venue:** IEEE APEC, pp. 1951-1958.
- **Link:** [10.1109/APEC.2012.6166090](https://doi.org/10.1109/APEC.2012.6166090) (also https://ieeexplore.ieee.org/document/6166090/)
- **Headline figure:** 92.5 %
- **Exact conditions:** 240 W prototype, 200 V output from a 60-cell module (Vmpp 30 V); fixed-gain resonant SC stage plus a partial-power buck-boost for MPPT; auxiliary inductor for ZVS. Switching frequency and devices not verified.
- **In plain language:** An SC stage does most of the step-up while a small buck-boost trims it for MPPT. The '96-97 % SC buck-boost for PV' figure sometimes quoted could NOT be verified; this is the closest verified paper.
- **Verification:** VERIFIED (OpenAlex; conditions partly verified)

## Bidirectional GaN

### Analysis and Design of a Condensed Buck-Boost Converter Utilizing Monolithic Bidirectional GaN Switches

- **Authors:** A. Aron, P. Eliat-Eliat, J. Buonato, S. Coday (MIT) (2025). **Venue:** IEEE Trans. Power Electronics 41(1):1226-1240.
- **Link:** [10.1109/TPEL.2025.3604743](https://doi.org/10.1109/TPEL.2025.3604743) (also https://coday.mit.edu/wp-content/uploads/2025/09/Aron_TPEL_2025.pdf)
- **Headline figure:** ML-CoBB 95.4 % buck / 97.5 % boost peak; passive weight 2.85x lower than the NIBB
- **Exact conditions:** 1 kW-rated 3-level prototype, 200-500 V in, 270 V out, 100 kHz; 95.4 % at 500 -> 270 V and 97.5 % at 200 -> 270 V, both at 880 W. Return-path-inductor variant 97.3 % / 98.1 %. Bidirectional switch: Transphorm TP65F060WS (preliminary part). MEASURED EFFICIENCY EXCLUDES GATE-DRIVE LOSS.
- **In plain language:** Replacing some switches in a flying-capacitor buck-boost with single-chip bidirectional GaN switches cuts inductor weight about 3x at 95-98 % efficiency. News coverage: Power Electronics News, 7 Apr 2026.
- **Verification:** VERIFIED (author PDF, OpenAlex)

### CoolGaN BDS 650 V G5 (IGLT65R055B2, IGLT65R110B2) and 40 V BDS (IGK048B041S)

- **Authors:** Infineon Technologies (2025). **Venue:** product pages / datasheets.
- **Link:** [https://www.infineon.com/part/IGLT65R055B2](https://www.infineon.com/part/IGLT65R055B2)
- **Exact conditions:** 650 V TOLT parts announced May 2025; 40 V WLCSP part (4.8 mOhm max) available 2026. Neither class fits a 60 V solar input, which is why the flagship uses the Innoscience 100 V part.
- **In plain language:** Commercial monolithic bidirectional GaN switches.
- **Verification:** VERIFIED

### VGaN bidirectional 100 V switch INV100FQ030C

- **Authors:** Innoscience (2024). **Venue:** product page.
- **Link:** [https://www.innoscience.com/product/detail/11/549](https://www.innoscience.com/product/detail/11/549)
- **Exact conditions:** 100 V, 2.5/3.2 mOhm, 100 A, FCQFN 4x6 mm; product page only; gate structure to be confirmed in the datasheet.
- **In plain language:** The only verified 100 V-class monolithic bidirectional GaN switch; used for the flagship's disconnect and bypass.
- **Verification:** VERIFIED (product page)

## GaN buck-boost

### 600W Solar Power Optimizer Reference Design Based on GaN (TIDA-010949)

- **Authors:** Texas Instruments. **Venue:** TI design guide TIDUF99.
- **Link:** [https://www.ti.com/lit/pdf/tiduf99](https://www.ti.com/lit/pdf/tiduf99)
- **Headline figure:** 99.0 % peak switching; 99.5-99.6 % in pass-through
- **Exact conditions:** Four-switch buck-boost with 2x LMG2100R026 GaN half-bridges; 15-80 V in, 0-80 V out, up to 300 kHz. 99.0 % at 600 W, 15 A output (98.6 % at 18 A). 99.5 % (33 V in) and 99.6 % (43 V in) are a SHORT/pass-through state, not conversion. C2000 control-card power is subtracted (auxiliary power excluded). Not peer reviewed.
- **In plain language:** A vendor reference design: a GaN solar power optimizer at about 99 % while actually converting.
- **Verification:** VERIFIED (TI document)

### A 400W, 99.3% Efficient GaN Buck-Boost Converter

- **Authors:** M. Heydari, Q. Huang, A. Q. Huang (2023). **Venue:** IEEE APEC, pp. 2223-2230.
- **Link:** [10.1109/APEC43580.2023.10131616](https://doi.org/10.1109/APEC43580.2023.10131616)
- **Headline figure:** up to 99.3 % measured
- **Exact conditions:** 500 kHz GaN buck-boost, 400 W; ~110 W/cm^3 with one inductor choice, ~35 W/cm^3 with another. Input/output voltages, the exact 99.3 % operating point, device part numbers and gate-drive inclusion were NOT verified (full text inaccessible).
- **In plain language:** A GaN buck-boost at 500 kHz with up to 99.3 % measured efficiency; treat as the best verified ceiling for this class, conditions pending.
- **Verification:** PARTIAL

## Piezoelectric

### A Spurious-Free Piezoelectric Resonator Based 3.2 kW DC-DC Converter for EV On-Board Chargers

- **Authors:** E. Stolt, W. D. Braun, K. Nguyen, V. Chulukhadze, R. Lu, J. Rivas-Davila (2024). **Venue:** IEEE Trans. Power Electronics 39(2):2478-2488.
- **Link:** [10.1109/TPEL.2023.3334211](https://doi.org/10.1109/TPEL.2023.3334211) (also https://ieeexplore.ieee.org/document/10323185/)
- **Headline figure:** 3.2 kW at 97.7 %; 5.7 kW/cm^3 component power density
- **Exact conditions:** 450 V -> 220 V, four paralleled piezoelectric converters, ring-electrode resonator suppressing spurious modes. Resonator material, switching frequency, devices and gate-drive inclusion not verified from the abstract. Research stage.
- **In plain language:** Four vibrating-crystal converters in parallel deliver EV-charger power with no magnetic inductor.
- **Verification:** VERIFIED (abstract only)

### Enumeration and Analysis of DC-DC Converter Implementations Based on Piezoelectric Resonators

- **Authors:** J. D. Boles, J. J. Piel, D. J. Perreault (2021). **Venue:** IEEE Trans. Power Electronics 36(1):129-145.
- **Link:** [10.1109/TPEL.2020.3004147](https://doi.org/10.1109/TPEL.2020.3004147) (also https://per.mit.edu/wp-content/uploads/2023/10/JPtpelJan21_Boles_PiezoConvEnumeration.pdf)
- **Headline figure:** >99 % peak (abstract); >= 96 % over a wide range
- **Exact conditions:** Prototype 100-200 V in, 40-80 V out, up to ~25 W, 115-135 kHz; APC 790 resonator (APC 844 material, radial mode); EPC2019 GaN; TI UCC27611 driver. The >99 % operating point could not be confirmed as measured (an appendix gives >99 % at 100 V -> 60 V, 4 W, apparently calculated); the measured plot read (Vout = 40 V) shows ~90-98 %. Gate-drive inclusion not stated. Research stage.
- **In plain language:** Systematically lists every way to build a DC-DC converter around a piezoelectric resonator and identifies the high-efficiency switching sequences.
- **Verification:** PARTIAL (bibliographic VERIFIED; the >99 % figure is treated as calculated)

### A hybrid piezoelectric resonator-based DC-DC converter

- **Authors:** J.-Y. Ko, W.-C. B. Liu, P. P. Mercier (UC San Diego) (2026). **Venue:** Nature Communications 17:4054.
- **Link:** [10.1038/s41467-026-70494-0](https://doi.org/10.1038/s41467-026-70494-0) (also https://www.nature.com/articles/s41467-026-70494-0)
- **Headline figure:** 96.2 % peak at 48 V -> 4.8 V
- **Exact conditions:** 48 V in, 4.8 V out, 150 mA (~0.72 W); 115-129 kHz, inductive region; APC 841 PZT disc 20 mm x 0.25 mm; IC in 180 nm BCD; open-loop control from a C2000 DSP. Gate-drive and control power inclusion not stated. Reports 4x baseline output current and 81.6 % lower resonator current. Research stage.
- **In plain language:** Embedded flying capacitors move the piezo stage's best ratio from 2:1 to 3:1, reaching ~9:1 step-down efficiently.
- **Verification:** VERIFIED (publisher page and PMC full text)

## High-ratio hybrid SC

### A Regulated 48V-to-1V/100A 90.9%-Efficient Hybrid Converter for POL Applications in Data Centers and Telecommunication Systems

- **Authors:** R. Das, H.-P. Le (2019). **Venue:** IEEE APEC, pp. 1997-2001.
- **Link:** [10.1109/APEC.2019.8722246](https://doi.org/10.1109/APEC.2019.8722246) (also https://par.nsf.gov/servlets/purl/10094095)
- **Headline figure:** 90.9 % peak at 48 V -> 1 V
- **Exact conditions:** Dual-phase multi-inductor hybrid; 90.9 % at 1 V / 30 A (100 A max); 93.6 % at 2 V / 35 A; 95.3 % at 5 V / 40 A; EPC2015c and EPC2023, 1 uH inductors; GATE-DRIVE LOSSES INCLUDED; 440 W/in^3 at 1 V. Frequency partly verified (333 kHz optimal, 167 kHz measured setting).
- **In plain language:** An inductor-plus-capacitor hybrid steps 48 V directly to 1 V for processors at about 91 %.
- **Verification:** VERIFIED (author PDF)

## Flying-capacitor buck-boost

### A Three-Level Buck-Boost Converter With Planar Coupled Inductor and Common-Mode Noise Suppression

- **Authors:** Y. Cao, Y. Bai, V. Mitrovic, B. Fan, D. Dong, R. Burgos, D. Boroyevich, R. S. K. Moorthy, M. Chinthavali (2023). **Venue:** IEEE Trans. Power Electronics 38(9):10483-10500.
- **Link:** [10.1109/TPEL.2023.3279987](https://doi.org/10.1109/TPEL.2023.3279987)
- **Headline figure:** up to 25 dB common-mode noise reduction; 30 % lower winding loss
- **Exact conditions:** 30 kHz, 50 kW bidirectional platform; efficiency figure and exact voltages NOT verified.
- **In plain language:** A three-level (flying-capacitor) buck-boost at 50 kW with a planar coupled inductor: the same topology family as the flagship, at 100x the power.
- **Verification:** PARTIAL

## Medium voltage

### 99% Efficient 10 kV SiC-Based 7 kV/400 V DC Transformer for Future Data Centers

- **Authors:** D. Rothmund, T. Guillod, D. Bortis, J. W. Kolar (2019). **Venue:** IEEE J. Emerging and Selected Topics in Power Electronics 7(2).
- **Link:** [10.1109/JESTPE.2018.2886139](https://doi.org/10.1109/JESTPE.2018.2886139) (also https://ieeexplore.ieee.org/document/8571261/)
- **Headline figure:** 99.0 % DC-DC
- **Exact conditions:** 7 kV DC -> 400 V DC, 25 kW, 48 kHz; 10 kV SiC MOSFETs (Wolfspeed CPM3-10000-0350) and 3x paralleled 1.2 kV C2M0025120D; 99.0 % from 13 to 25.6 kW measured calorimetrically INCLUDING auxiliaries and cooling; 98.1 % for the full solid-state transformer. A series-resonant DC transformer, NOT a flying-capacitor multilevel converter.
- **In plain language:** A single 10 kV SiC stage turns medium-voltage DC into 400 V with about 1 % loss.
- **Verification:** VERIFIED (author PDF)

## Solar weighting

### European or CEC efficiency (PVsyst documentation)

- **Authors:** PVsyst SA (2026). **Venue:** PVsyst help.
- **Link:** [https://www.pvsyst.com/help/component-database/grid-inverters/grid-inverters-main-interface/grid-inverters-efficiency-curve/european-or-cec-efficiency.html](https://www.pvsyst.com/help/component-database/grid-inverters/grid-inverters-main-interface/grid-inverters-efficiency-curve/european-or-cec-efficiency.html)
- **Headline figure:** CEC = .04n10+.05n20+.12n30+.21n50+.53n75+.05n100; Euro = .03n5+.06n10+.13n20+.10n30+.48n50+.20n100
- **Exact conditions:** Secondary source; the primary CEC/Sandia protocol document was not reached. CEC also averages over three DC voltages (not verified here).
- **In plain language:** Weights used for the weighted-efficiency numbers.
- **Verification:** VERIFIED (secondary source)

## Component data

Device parameters live in `data/devices.json`; each entry lists which fields were checked against the manufacturer datasheet (`verified`) and explains every estimate (`notes`). The flagship bill of materials, with a status column, is `hardware/flagship/BOM.csv`.

## Open-source tools used or referenced

| Tool | Use here | License note |
|---|---|---|
| [ngspice](https://ngspice.sourceforge.io) | desktop simulation back end; cross-checks the Python circuit simulation | BSD-3 style; invoked as an external program, not bundled |
| [KiCad](https://gitlab.com/kicad/code/kicad) | schematic / BOM conventions for the reference design | GPL-3; conventions only, no code copied |
| [Apache ECharts](https://github.com/apache/echarts), [plotly.js](https://github.com/plotly/plotly.js) | considered for charts; the site ships its own small SVG charts instead so it can run under a strict CSP with zero third-party scripts | Apache-2 / MIT |
| IEEE TPEL / APEC / COMPEL papers | every topology and loss reference above, cited by DOI | publisher copyright; cited, never reproduced |

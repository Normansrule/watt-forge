# Equations and where they are checked

Every equation in the course follows the same pattern: intuition, equation, symbols with units, a worked example, a visual, and a passing test. The full explanations live in the web lessons (`site/learn-*.html`). This table indexes each equation to its implementation and to the test that checks its worked example numerically.

| Equation | Implementation | Worked example (checked) | Test |
|---|---|---|---|
| Duty cycle, ideal ratios: buck D, boost 1/(1-D), buck-boost -D/(1-D), SEPIC, Cuk, flyback nD/(1-D), four-switch D1/(1-D2) | `ratios.py`, `core.js` | 48->12 V needs D = 0.25; 24->48 V needs D = 0.5 | `test_ratios.py::test_ideal_ratios_worked_examples` |
| Ratios with resistance, e.g. boost M = 1/(1-D) / (1 + (Ron+RL)/((1-D)^2 R)) | `ratios.py` | D = 0.5, R = 10, 50 mOhm: M = 1.961 | `test_lossy_ratio_worked_example`, `test_lossy_buck_ratio_against_ngspice` (ngspice) |
| Volt-second balance <vL> = 0; charge balance <iC> = 0 | `ratios.py` | buck 48->12 at D = 0.25 balances; boost IL = Iout/(1-D) | `test_volt_second_and_charge_balance` |
| CCM/DCM: K = 2L/(R Ts) vs K_crit(D); DCM ratios | `ratios.py` | DCM formula equals CCM ratio at K = K_crit | `test_ccm_dcm_boundary_is_continuous` |
| Sizing: L = (Vin-Vout) D/(dI fs); C = dI/(8 fs dV) | `ratios.py` | 15 uH; 15.625 uF | `test_sizing_worked_example` |
| Conduction P = Irms^2 R, Irms^2 = D(I^2 + dI^2/12) | `losses.py` | 10 A, 5 mOhm: 0.5 W; 25.1875 A^2 | `test_losses.py::test_conduction_worked_example` |
| Overlap 1/2 V I (ton+toff) f | `losses.py` | 0.96 W | `test_switching_worked_examples` |
| Coss: 1/2 Coss V^2 f; half-bridge hard turn-on Qoss(V) V f; Eoss = m/(m+1) Q V | `losses.py`, `devices.py` | 0.2304 W / 0.4608 W; EPC2361 fit reproduces Co(er), Co(tr) to 1 % | `test_switching_worked_examples`, `test_qoss_exponent_fit_reproduces_datasheet` |
| ZVS condition \|i\| t_dead >= 2 Qoss | `losses.py` | 12 A x 10 ns = 2 x 60 nC | `test_zvs_residual` |
| Reverse recovery Qrr V f; gate Qg Vdrv f; dead time Vsd I td f n | `losses.py` | 0.2688 W; 14 mW; 40 mW | `test_switching_worked_examples` |
| Steinmetz k f^a B^b; iGSE | `magnetics.py`, `core.js` | iGSE(sinusoid) = Steinmetz to 0.2 % | `test_steinmetz_and_igse` |
| Switched capacitor: R_SSL = sum a_c^2/(C f), R_FSL = 2 sum R a_r^2 | `switched_cap.py` | 48 V -> 23.5 V, 10 uF, 100 kHz: 0.25 ohm, 2 A, 1.0 W | `test_switched_capacitor_limits` (exact periodic solution + brute-force integration) |
| Efficiency eta = Pout/(Pout + sum P_loss); CEC and Euro weighting | `efficiency.py` | weighted sums of a sample curve | `test_efficiency_and_weighting` |
| Three-level ripple: (Vin - Vout)(D - 1/2) Ts/L for D > 1/2, (Vin/2 - Vout) D Ts/L for D < 1/2; zero at D = 1/2 | `flagship/pwm.py` | exact | `test_flagship_model.py::test_three_level_ripple_formula` |
| Flagship loss model vs circuit simulation vs ngspice | `flagship/model.py`, `flagship/sim.py`, `spice.py` | agreement within 0.15 points (model vs simulation) and 5e-5 (simulation vs ngspice) | `test_flagship_sim.py` |

The browser implementation (`docs/js/model/*.js`) is checked against the Python implementation on 1,751 values, including a 1,400-tick controller trace (`tests/js/parity.mjs`).

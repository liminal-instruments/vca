"""Three-trimmer calibration of the 8T cell built from BCM847DS/BCM857DS models.
Run from sim/:  ../.venv/bin/python study_trim.py            (ideal op-amps, ideal bias source)
                ../.venv/bin/python study_trim.py OPA1678    (buildable cell, real op-amp model)"""
import sys
import numpy as np
from scipy.optimize import minimize_scalar
from harness import *

A = 2 ** 0.5
S = 5.92e-3                      # V/dB, nominal
OA = sys.argv[1] if len(sys.argv) > 1 else "ideal"
CELL = "BLACKMER8" if OA == "ideal" else "BLACKMER8D"
HDR = header("bjt_bcm.lib", oa_in=OA, oa_out=OA)
VT = 0.025865
POINTS = [(3.16, -30), (3.16, -15), (1, -6), (1, 0), (3.16, 0), (1, 6), (0.562, 15), (0.1, 30)]

def meas(core, pots, vin, g):
    f, h, t, dc = thd_run(vin * A, g * S, hdr=HDR, fixture=vca_fixture(CELL, core, **pots), full=True)
    return t * 100, 20 * np.log10(f / (vin * A)), dc

def opt(core, pots, which, vin, g):
    r = minimize_scalar(lambda p: meas(core, {**pots, which: p}, vin, g)[0],
                        bounds=(0.02, 0.98), method="bounded", options={"xatol": 1e-4})
    return {**pots, which: r.x}

def trim(core):
    pots = dict(sym=0.5, slope=0.5, gain=0.5)
    for _ in range(2):                                   # two passes: the trims interact slightly
        pots = opt(core, pots, "sym", 1.0, 0)            # 1) symmetry at 0 dB, 1 Vrms
        pots = opt(core, pots, "slope", 3.16, -15)       # 2) slope symmetry at -15 dB, +10 dBV
    # 3) gain pot: 0 dB at Ec = 0 (secant on measured gain)
    g0 = meas(core, pots, 1.0, 0)[1]
    g1 = meas(core, {**pots, "gain": 0.6}, 1.0, 0)[1]
    pots["gain"] = 0.5 - g0 * 0.1 / (g1 - g0)
    return pots

def report(label, core):
    print(f"\n=== {label}")
    untr = dict(sym=0.5, slope=0.5, gain=0.5)
    pots = trim(core)
    print(f"  trimmer positions: sym {pots['sym']:.4f}  slope {pots['slope']:.4f}  gain {pots['gain']:.4f}")
    print("   Vin(Vrms) gain(dB) | untrimmed THD   gain err | trimmed THD   gain err   DC out")
    for vin, g in POINTS:
        u = meas(core, untr, vin, g); t = meas(core, pots, vin, g)
        print(f"   {vin:6.3f}   {g:+4d}     |   {u[0]:8.4f} %   {u[1]-g:+6.3f}  |  {t[0]:8.5f} %  {t[1]-g:+6.3f}  {t[2]*1e3:+7.3f} mV")

ar = lambda mv: np.exp(mv * 1e-3 / VT)
BASE = "CC=22p GBW=10e6 RC=1.75" if OA == "ideal" else "RDRV=1000 CC=22p RC=1.75"
print(f"cell {CELL}, op-amps {OA}, {BASE}")
if OA == "ideal":
    report("perfectly matched pairs", BASE)
report("pairs at datasheet-limit mismatch (Q2 +2 mV, Q4 -1.5 mV, Q6 -1 mV, Q8 +2 mV)",
       f"{BASE} AR2={ar(2):.5f} AR4={ar(-1.5):.5f} AR6={ar(-1):.5f} AR8={ar(2):.5f}")

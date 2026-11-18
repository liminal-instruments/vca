"""4-transistor vs 8-transistor cell, ideal vs BCM847DS/BCM857DS devices, all pairs perfectly matched.
Run from the project root:  .venv/bin/python sim/study_cells.py"""
import numpy as np
from harness import *

A = 2 ** 0.5
POINTS = [(1.0, 0), (3.16, 0), (3.16, -15), (0.562, 15), (3.16, -30), (0.1, 30)]   # (Vin rms, gain dB)

def dc_gain(hdr, fix, vin):
    net = f"{hdr}\nVin vin 0 {vin}\nVecp ecp 0 0\n{fix}\n.control\ndc Vecp -0.09 0.09 0.005\nwrdata {{out}} v(vo)\n.endc\n.end\n"
    r = run(net, {"out": "o.txt"})["out"]
    g = 20 * np.log10(r[:, 1] / vin)
    return np.polyfit(r[:, 0], g, 1)       # dB/V, dB at 0

def table(devs, cell, params, label):
    hdr = header(devs)
    fix = vca_fixture(cell, params)
    sp, op = dc_gain(hdr, fix, 1.0)
    sn, on = dc_gain(hdr, fix, -1.0)
    print(f"\n{label}")
    print(f"  control law: +half {1e3/sp:.4f} mV/dB, -half {1e3/sn:.4f} mV/dB   gain at Ec=0: {op:+.3f} / {on:+.3f} dB")
    s = (sp + sn) / 2
    for vin, g in POINTS:
        f, h, thd, dc = thd_run(vin * A, g / s, hdr=hdr, fixture=fix, full=True)
        print(f"  Vin {vin:5.3f} Vrms  gain {20*np.log10(f/(vin*A)):+7.2f} dB  THD {thd*100:8.5f} %  "
              f"H2 {20*np.log10(h[0]/f+1e-30):6.1f}  H3 {20*np.log10(h[1]/f+1e-30):6.1f} dBc  DC out {dc*1e3:+8.3f} mV")

AMP = "CC=22p GBW=10e6"
table("bjt_ideal.lib", "BLACKMER4", AMP, "IDEAL devices, 4T cell")
table("bjt_ideal.lib", "BLACKMER8", AMP, "IDEAL devices, 8T cell (RC ~ 0)")
table("bjt_bcm.lib", "BLACKMER4", AMP, "BCM847/857, 4T cell")
table("bjt_bcm.lib", "BLACKMER8", AMP, "BCM847/857, 8T cell, RC ~ 0")
for rc in (0.5, 1.0, 1.5, 2.0):
    table("bjt_bcm.lib", "BLACKMER8", f"{AMP} RC={rc}", f"BCM847/857, 8T cell, RC = {rc} ohm")

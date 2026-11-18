"""Input-amplifier compensation for the discrete cell: stability vs distortion.
Run from sim/:  ../.venv/bin/python study_comp.py [OPAMP]"""
import sys, numpy as np
from harness import *

OA = sys.argv[1] if len(sys.argv) > 1 else "OPA1678"
A = 2 ** 0.5; S = 5.92e-3
hdr = header("bjt_bcm.lib", oa_in=OA, oa_out=OA)
LEVELS = [(g, v) for g in (-20, 0, 20) for v in (0, 0.05, -0.05, 0.5, -0.5, 3, -3, 10, -10) if not (g == 20 and abs(v) > 1)]
print(f"op-amp: {OA}.  stability = worst closed-loop peaking over instantaneous input levels 0..+-10 V at -20/0/+20 dB")
print(" RDRV    CC   | worst peak (dB) at f, [gain, Vin] | min BW  | THD 1k 1V 0dB | 10k 1V 0dB | 1k 3.16V 0dB | 1k .562V +15dB | 10k .562V +15dB")
for rdrv, cc in [(1, "22p"), (1, "330p"), (470, "47p"), (1000, "10p"), (1000, "22p"), (1000, "47p"), (2200, "10p"), (2200, "22p"), (2200, "4.7p")]:
    fix = vca_fixture("BLACKMER8D", f"RDRV={rdrv} CC={cc}")
    worst = (-1, 0, None); bw = 1e12; nfail = 0
    for g, vdc in LEVELS:
        try:
            p, fp, b = ac_peaking(vdc, g * S, hdr, fix)
        except RuntimeError:          # DC operating point did not converge (vendor macromodel)
            nfail += 1; continue
        if p > worst[0]: worst = (p, fp, (g, vdc))
        if b == b: bw = min(bw, b)
    def t(v, g, f0):
        try:
            return f"{thd_run(v*A, g*S, f0=f0, hdr=hdr, fixture=fix)[2]*100:8.5f}%"
        except Exception:
            return "   FAIL  "
    print(f" {rdrv:5d} {cc:>5s} | {worst[0]:6.1f} dB at {worst[1]/1e6:6.2f} MHz {str(worst[2]):12s} ({nfail:2d} n/c) | {bw/1e3:5.0f}k  |  {t(1,0,1e3)}   | {t(1,0,1e4)}  |  {t(3.16,0,1e3)}   |   {t(.562,15,1e3)}    |   {t(.562,15,1e4)}")

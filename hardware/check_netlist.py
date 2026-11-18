#!/usr/bin/env python3
"""Check the KiCad schematic against the simulated circuit.

Exports the netlist with kicad-cli and compares its connectivity with the netlist below, which
was written by hand from sim/lib/blackmer8d.lib and vca_fixture() in sim/harness.py
(independently of the drawing code in gen_schematic.py). Two-pin parts (R, C) are treated as
unpolarised. Exit status 0 = identical.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCH = Path(__file__).parent / "blackmer_vca" / "blackmer_vca.kicad_sch"

# Dual transistor packages (E1 B1 C2 E2 B2 C1 = pins 1..6): unit A = C6 B2 E1, unit B = C3 B5 E4.
# Q1 = sim Q1/Q2, Q2 = sim Q3/Q4, Q3 = sim Q5/Q6, Q4 = sim Q7/Q8, Q5 = D1/D2, Q6 = D3/QS, Q7 = QP (1 B, 2 E, 3 C)
# R1 Rin, R2 Rf, R3 RDRV, R4..R7 RC1..RC4, R8 RSTR, R9 RPB, R10 RSINK, R11 Rsym, R12 sim R1, R13 sim R3,
# R14 Rslope, R15 Rgain, R16 Rg1, C1 CC, C2 Cf.  U1: 1 outA 2 -A 3 +A 4 V- 5 +B 6 -B 7 outB 8 V+
EXPECTED = {
    "in":  "R1 U1.2 C1 Q1.6 Q2.6",
    "vin": "R1 J2.1",
    "oa":  "U1.1 C1 R3",
    "top": "R3 R6 R7 Q5.1 R9 Q7.2 TP2.1",
    "bot": "R4 R5 R8 Q6.4 Q7.3 R10 TP3.1",
    "ecn": "Q1.2 Q2.5 R15 R16",
    "sym": "Q1.5 R11 R12 RV2.1 TP5.1",
    "b3":  "Q2.2 R13 RV2.3",
    "ecp": "R12 R13 J3.1 TP4.1",
    "out": "Q1.3 Q2.3 U1.6 R2 C2",
    "vo":  "U1.7 R2 C2 J4.1 TP1.1",
    "e1":  "Q1.1 Q3.1",
    "e2":  "Q1.4 Q3.4",
    "e3":  "Q2.1 Q4.1",
    "e4":  "Q2.4 Q4.4",
    "c5":  "Q3.6 Q3.5 R4",
    "c6":  "Q3.3 Q3.2 R5",
    "c7":  "Q4.6 Q4.5 R6",
    "c8":  "Q4.3 Q4.2 R7",
    "d1":  "Q5.6 Q5.2 Q5.4",
    "d2":  "Q5.3 Q5.5 Q6.6 Q6.2",
    "x":   "Q6.1 R8 Q6.5",
    "qb":  "Q6.3 R9 Q7.1",
    "ws":  "RV1.2 R11",
    "wl":  "RV2.2 R14",
    "wg":  "RV3.2 R15",
    "+15": "U1.8 RV1.1 RV3.1 C3 C5 J1.1",
    "-15": "U1.4 RV1.3 RV3.3 C4 C6 J1.3 R10",
    "gnd": "U1.3 U1.5 R14 R16 C3 C4 C5 C6 J1.2 J2.2 J3.2 J4.2 TP6.1",
}


def kicad_nets():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                        "-o", str(out), str(SCH)], check=True, capture_output=True)
        text = out.read_text()
    nets = {}
    for chunk in text.split("(net (code")[1:]:
        name = re.search(r'\(name "([^"]*)"', chunk).group(1)
        nets[name] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', chunk)
    return nets


def token(ref, pin):
    return ref if re.match(r"[RC]\d", ref) else f"{ref}.{pin}"


got = {frozenset(token(r, p) for r, p in nodes): name for name, nodes in kicad_nets().items()}
want = {frozenset(v.split()): k for k, v in EXPECTED.items()}
npins = sum(len(k) for k in got)
ok = set(got) == set(want)
for k in set(want) - set(got):
    print(f"MISSING  {want[k]:4s}: {' '.join(sorted(k))}")
for k in set(got) - set(want):
    print(f"EXTRA    {got[k]}: {' '.join(sorted(k))}")
print(f"{len(got)} nets, {npins} pin connections in schematic; {len(want)} nets expected ->",
      "MATCH" if ok else "MISMATCH")
sys.exit(0 if ok else 1)

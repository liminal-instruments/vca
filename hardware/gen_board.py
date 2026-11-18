#!/usr/bin/env python3
"""Create the starting-point PCB for the 2181-pinout module: footprints placed and linked to the
schematic, nets assigned, board outline, ground pours on both sides. No tracks are routed.

    python3 gen_board.py        -> blackmer_vca/blackmer_vca.kicad_pcb   (OVERWRITES the board)

Then run route_board.py for a first-pass routing. Once you edit the board by hand, stop running
both scripts and work in KiCad
("Update PCB from Schematic" keeps working because footprints carry the schematic links).
"""
import re
import subprocess
import tempfile
from pathlib import Path

import pcbnew

HERE = Path(__file__).parent / "blackmer_vca"
SCH = HERE / "blackmer_vca.kicad_sch"
PCB = HERE / "blackmer_vca.kicad_pcb"
FPDIR = Path("/usr/share/kicad/footprints")
OX, OY = 100.0, 80.0            # board origin on the sheet (mm)
W, H = 56.0, 38.0               # board size (mm)
PITCH = 2.54
PIN1 = ((W - 7 * PITCH) / 2, H - 2.54)   # SIP row centred on the bottom edge, 0.1 in pitch

# ---- placement (mm from the board's top-left corner; rotation in degrees)
# The six matched-pair packages form one tight 3 x 2 block so they share a temperature; the
# op-amp (the only real heat source, about 0.1 W) is at the far left, trimmers at the far right.
PLACE = {
    "U1": (6.5, 17, 0), "C3": (6.5, 11.5, 0), "C4": (6.5, 22.5, 0),
    "C1": (12, 14.5, 0), "R3": (12, 17.5, 0),
    "Q4": (18.5, 15, 0), "Q2": (26, 15, 0), "Q5": (33.5, 15, 0),
    "Q3": (18.5, 21, 0), "Q1": (26, 21, 0), "Q6": (33.5, 21, 0),
    "R6": (17.5, 10.8, 90), "R7": (19.5, 10.8, 90),
    "R4": (17.5, 25.2, 90), "R5": (19.5, 25.2, 90),
    "Q7": (39.8, 21, 0), "R8": (39.8, 17.5, 0), "R9": (39.8, 15.3, 0),
    "R11": (45, 7, 0), "R12": (45, 12, 0), "R13": (45, 14, 0), "R14": (45, 16, 0),
    "R15": (45, 21, 0), "R16": (45, 23, 0),
    "RV1": (50.5, 7, 0), "RV2": (50.5, 14, 0), "RV3": (50.5, 21, 0),
    "R10": (PIN1[0] + 4 * PITCH, 30.5, 0),
    "J1": (PIN1[0], PIN1[1], 90), "J2": (47, PIN1[1], 0), "JP1": (47, 30, 0),
    "TP1": (4.5, 27, 0), "TP2": (8.5, 27, 0), "TP3": (4.5, 31, 0), "TP4": (8.5, 31, 0), "TP5": (4.5, 35, 0),
}
PIN_NAMES = ["IN", "EC+", "EC-", "SYM", "V-", "GND", "V+", "OUT"]


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def netlist():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                        "-o", str(out), str(SCH)], check=True, capture_output=True)
        text = out.read_text()
    comps = {}
    for chunk in text.split("(comp (ref ")[1:]:
        ref = re.match(r'"([^"]+)"', chunk).group(1)
        comps[ref] = dict(value=re.search(r'\(value "([^"]*)"', chunk).group(1),
                          footprint=re.search(r'\(footprint "([^"]*)"', chunk).group(1),
                          tstamp=re.search(r'\(tstamps "([^"]+)"', chunk).group(1))
    pads = {}
    for chunk in text.split("(net (code")[1:]:
        name = re.search(r'\(name "([^"]*)"', chunk).group(1)
        for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', chunk):
            pads[(ref, pin)] = name
    return comps, pads


def text(board, s, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetPosition(mm(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    board.Add(t)


comps, padnets = netlist()
missing = set(comps) - set(PLACE)
assert not missing, f"no placement for {missing}"
board = pcbnew.CreateEmptyBoard()

nets = {}
for name in sorted(set(padnets.values())):
    nets[name] = pcbnew.NETINFO_ITEM(board, name)
    board.Add(nets[name])

for ref, c in sorted(comps.items()):
    lib, name = c["footprint"].split(":")
    fp = pcbnew.FootprintLoad(str(FPDIR / f"{lib}.pretty"), name)
    assert fp, c["footprint"]
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    fp.SetPath(pcbnew.KIID_PATH(f"/{c['tstamp']}"))          # link to the schematic symbol
    x, y, rot = PLACE[ref]
    board.Add(fp)
    fp.SetPosition(mm(x, y))
    fp.SetOrientationDegrees(rot)
    for pad in fp.Pads():
        net = padnets.get((ref, pad.GetNumber()))
        if net:
            pad.SetNet(nets[net])

# the SIP row must run left to right, pin 1 first, on a 0.1 in pitch
j1 = board.FindFootprintByReference("J1")
xs = {p.GetNumber(): pcbnew.ToMM(p.GetPosition().x) - OX for p in j1.Pads()}
if xs["8"] < xs["1"]:
    j1.SetOrientationDegrees(-90)
    xs = {p.GetNumber(): pcbnew.ToMM(p.GetPosition().x) - OX for p in j1.Pads()}
assert abs(xs["8"] - xs["1"] - 7 * PITCH) < 1e-3, xs

# outline
edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetStart(mm(0, 0))
edge.SetEnd(mm(W, H))
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetWidth(pcbnew.FromMM(0.1))
board.Add(edge)

# ground pours, both sides
zones = []
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(nets["GND"])
    z.SetZoneName("GND")
    o = z.Outline()
    o.NewOutline()
    for x, y in ((0, 0), (W, 0), (W, H), (0, H)):
        p = mm(x, y)
        o.Append(p.x, p.y)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetMinThickness(pcbnew.FromMM(0.25))
    z.SetLocalClearance(pcbnew.FromMM(0.3))
    board.Add(z)
    zones.append(z)

# silkscreen
for i, n in enumerate(PIN_NAMES):
    text(board, n, PIN1[0] + i * PITCH, PIN1[1] - 3.6, size=0.8, rot=90)
text(board, "Discrete Blackmer VCA r0.2 - 2181 pinout", 18, 2.2, size=1.0)
text(board, "SYM", 50.5, 10.2, size=0.8)
text(board, "SLOPE", 50.5, 17.2, size=0.8)
text(board, "GAIN", 50.5, 24.2, size=0.8)
text(board, "-15V", 51.3, PIN1[1], size=0.8)

# zones are left unfilled: press B in the PCB editor (filling from a script crashes KiCad 9 headless)
pcbnew.SaveBoard(str(PCB), board)
print(f"wrote {PCB}: {len(comps)} footprints, {len(nets)} nets, board {W:g} x {H:g} mm, "
      f"SIP pins at x = {xs['1']:.2f} .. {xs['8']:.2f} mm")

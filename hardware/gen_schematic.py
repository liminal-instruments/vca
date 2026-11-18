#!/usr/bin/env python3
"""Generate the KiCad 9 schematic of the discrete Blackmer VCA prototype (one channel).

The circuit is the simulated BLACKMER8D cell (sim/lib/blackmer8d.lib) plus the three-trimmer
fixture from sim/harness.py, with board-level additions (connectors, decoupling, test points).

    python3 gen_schematic.py          -> blackmer_vca/blackmer_vca.kicad_sch (+ .kicad_pro)

All coordinates below are in units of 1.27 mm ("u"). check_netlist.py verifies the result
against an independently written netlist.
"""
import math
import re
import uuid
from pathlib import Path

SYMDIR = Path("/usr/share/kicad/symbols")
OUT = Path(__file__).parent / "blackmer_vca"
PROJECT = "blackmer_vca"
U = 1.27
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "blackmer-vca-root"))
_n = 0


def uid():
    global _n
    _n += 1
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"blackmer-vca-{_n}"))


def mm(v):
    return f"{v * U:.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- symbol library access
def _block(text, start):
    """Return the balanced s-expression starting at text[start] == '('."""
    depth, i, instr = 0, start, False
    while i < len(text):
        c = text[i]
        if instr:
            if c == "\\":
                i += 1
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced")


_libtext = {}
_symcache = {}


def lib_symbol(lib_id):
    """-> (embedded s-expr text, {unit: {pin number: (x, y, name)}}) with 'extends' flattened."""
    if lib_id in _symcache:
        return _symcache[lib_id]
    lib, name = lib_id.split(":")
    text = _libtext.setdefault(lib, (SYMDIR / f"{lib}.kicad_sym").read_text())

    def raw(nm):
        return _block(text, text.index(f'\n\t(symbol "{nm}"\n') + 2)

    blk = raw(name)
    m = re.search(r'\(extends "([^"]+)"\)', blk)
    if m:
        parent = m.group(1)
        blk = raw(parent).replace(f'(symbol "{parent}"', f'(symbol "{name}"', 1)
        blk = blk.replace(f'(symbol "{parent}_', f'(symbol "{name}_')
    pins = {}
    for sm in re.finditer(r'\(symbol "%s_(\d+)_\d+"' % re.escape(name), blk):
        sub = _block(blk, sm.start())
        unit = int(sm.group(1))
        for pm in re.finditer(r"\(pin\s", sub):
            p = _block(sub, pm.start())
            x, y = map(float, re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)", p).groups())
            num = re.search(r'\(number\s+"([^"]*)"', p).group(1)
            nm = re.search(r'\(name\s+"([^"]*)"', p).group(1)
            pins.setdefault(unit, {})[num] = (x / U, y / U, nm)
    emb = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    _symcache[lib_id] = (emb, pins)
    return _symcache[lib_id]


# ---------------------------------------------------------------- schematic model
class Sch:
    def __init__(self):
        self.items, self.wires, self.pinpts, self.used, self.pwr = [], [], [], [], 0

    def place(self, lib_id, ref, value, x, y, rot=0, mirror=None, unit=1, fp="",
              ref_at=(2.0, -1.3, "left"), val_at=(2.0, 1.3, "left"), show_ref=True, show_val=True):
        emb, pins = lib_symbol(lib_id)
        if lib_id not in self.used:
            self.used.append(lib_id)
        out = {}
        allpins = dict(pins.get(0, {}))
        allpins.update(pins.get(unit, {}))
        for num, (px, py, nm) in allpins.items():
            a = math.radians(rot)                      # KiCad rotates first, then mirrors
            rx = px * math.cos(a) - py * math.sin(a)
            ry = px * math.sin(a) + py * math.cos(a)
            if mirror == "x":
                ry = -ry
            elif mirror == "y":
                rx = -rx
            pt = (round(x + rx), round(y - ry))
            out[num] = pt
            out[nm] = pt
            self.pinpts.append(pt)

        def prop(name, val, at, show):
            dx, dy, just = at
            j = "" if just == "center" else f" (justify {just})"
            hide = "" if show else " (hide yes)"
            ang = 90 if rot in (90, 270) else 0
            return (f'\t\t(property "{name}" "{val}" (at {x * U + dx:.3f} {y * U + dy:.3f} {ang})\n'
                    f'\t\t\t(effects (font (size 1.27 1.27)){j}{hide}))\n')

        s = f'\t(symbol (lib_id "{lib_id}") (at {mm(x)} {mm(y)} {rot})'
        if mirror:
            s += f" (mirror {mirror})"
        s += (f" (unit {unit})\n\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n"
              f'\t\t(uuid "{uid()}")\n')
        s += prop("Reference", ref, ref_at, show_ref)
        s += prop("Value", value, val_at, show_val)
        s += prop("Footprint", fp, (0, 0, "center"), False)
        s += prop("Datasheet", "", (0, 0, "center"), False)
        for num in sorted({n for u_ in pins for n in pins[u_]}):
            s += f'\t\t(pin "{num}" (uuid "{uid()}"))\n'
        s += (f'\t\t(instances (project "{PROJECT}" (path "/{ROOT_UUID}" '
              f'(reference "{ref}") (unit {unit}))))\n\t)\n')
        self.items.append(s)
        return out

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            assert a[0] == b[0] or a[1] == b[1], (a, b)
            if a != b:
                self.wires.append((a, b))

    def label(self, name, pt, rot=0, just="left bottom"):
        self.items.append(f'\t(label "{name}" (at {mm(pt[0])} {mm(pt[1])} {rot})\n'
                          f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
                          f'\t\t(uuid "{uid()}"))\n')

    def text(self, s, x, y, size=1.27, bold=False):
        s = s.replace("\n", "\\n")
        b = " (bold yes)" if bold else ""
        self.items.append(f'\t(text "{s}" (exclude_from_sim no) (at {mm(x)} {mm(y)} 0)\n'
                          f'\t\t(effects (font (size {size} {size}){b}) (justify left top))\n'
                          f'\t\t(uuid "{uid()}"))\n')

    def power(self, name, pt, rot=0):
        self.pwr += 1
        dy = 3.8 if (name == "GND") != (rot == 180) else -3.6
        if name == "-15V":
            dy = -dy if rot == 0 else dy
        self.place(f"power:{name}", f"#PWR{self.pwr:02d}", name, pt[0], pt[1], rot=rot,
                   show_ref=False, val_at=(0, dy, "center"))

    def flag(self, pt):
        self.pwr += 1
        self.place("power:PWR_FLAG", f"#FLG{self.pwr:02d}", "PWR_FLAG", pt[0], pt[1],
                   show_ref=False, show_val=False)

    # ---- helpers for common parts
    def r(self, ref, value, x, y, horiz=False, fp="Resistor_SMD:R_0603_1608Metric"):
        if horiz:
            p = self.place("Device:R", ref, value, x, y, rot=90, fp=fp,
                           ref_at=(0, -2.5, "center"), val_at=(0, 2.5, "center"))
            return (x - 3, y), (x + 3, y)
        self.place("Device:R", ref, value, x, y, fp=fp)
        return (x, y - 3), (x, y + 3)

    def c(self, ref, value, x, y, horiz=False, fp="Capacitor_SMD:C_0603_1608Metric"):
        if horiz:
            self.place("Device:C", ref, value, x, y, rot=90, fp=fp,
                       ref_at=(0, -3.6, "center"), val_at=(0, 3.6, "center"))
            return (x - 3, y), (x + 3, y)
        self.place("Device:C", ref, value, x, y, fp=fp,
                   ref_at=(2.6, -1.3, "left"), val_at=(2.6, 1.3, "left"))
        return (x, y - 3), (x, y + 3)

    def q(self, ref, unit, kind, value, ce_x, y, base="L", e_up=False):
        """Transistor with its collector/emitter line at x = ce_x. Returns {'B','C','E'} points."""
        if unit:
            lib = f"Transistor_BJT:Q_Dual_{kind}_{kind}_E1B1C2E2B2C1"
            fp = "Package_TO_SOT_SMD:SC-74-6_1.55x2.9mm_P0.95mm"
        else:
            lib, unit, fp = f"Transistor_BJT:Q_{kind}_BEC", 1, "Package_TO_SOT_SMD:SOT-23"
        pins = lib_symbol(lib)[1][unit]
        byname = {nm[0]: (px, py) for px, py, nm in pins.values()}
        flip_h = base == "R"
        flip_v = (byname["E"][1] > 0) != e_up
        rot, mirror = (180, None) if (flip_h and flip_v) else (0, "y" if flip_h else "x" if flip_v else None)
        x0 = ce_x + 2 if flip_h else ce_x - 2
        side = -1 if flip_h else 1
        just = "left"                              # KiCad mirrors the justification with the symbol
        p = self.place(lib, ref, value, x0, y, rot=rot, mirror=mirror, unit=unit, fp=fp,
                       ref_at=(side * 5.4, -1.3, just), val_at=(side * 5.4, 1.3, just))
        res = {}
        for num, (px, py, nm) in pins.items():
            res[nm[0]] = p[num]
        assert res["C"][0] == ce_x and res["E"][0] == ce_x, res
        return res

    # ---- output
    def junctions(self):
        ends = {}
        for a, b in self.wires:
            for p in (a, b):
                ends[p] = ends.get(p, 0) + 1
        js = set()
        for p in set(ends) | set(self.pinpts):
            n = ends.get(p, 0) + self.pinpts.count(p)
            inside = any((a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1])) or
                         (a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0]))
                         for a, b in self.wires)
            if n >= 3:
                js.add(p)
        return js

    def write(self, title, rev):
        libs = "".join("\t\t" + lib_symbol(l)[0].replace("\n", "\n\t") + "\n" for l in self.used)
        body = "".join(self.items)
        # KiCad expects wires to be broken wherever something connects to them
        pts = {p for w in self.wires for p in w} | set(self.pinpts)
        split = []
        for a, b in self.wires:
            on = sorted(p for p in pts if (a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1]))
                        or (a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0])))
            chain = [min(a, b)] + on + [max(a, b)]
            split += list(zip(chain, chain[1:]))
        self.wires = split
        for a, b in self.wires:
            body += (f"\t(wire (pts (xy {mm(a[0])} {mm(a[1])}) (xy {mm(b[0])} {mm(b[1])}))\n"
                     f'\t\t(stroke (width 0) (type default)) (uuid "{uid()}"))\n')
        for p in sorted(self.junctions()):
            body += (f"\t(junction (at {mm(p[0])} {mm(p[1])}) (diameter 0) (color 0 0 0 0)"
                     f' (uuid "{uid()}"))\n')
        sch = (f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n'
               f'\t(generator_version "9.0")\n\t(uuid "{ROOT_UUID}")\n\t(paper "A3")\n'
               f'\t(title_block\n\t\t(title "{title}")\n\t\t(rev "{rev}")\n'
               f'\t\t(comment 1 "Generated by hardware/gen_schematic.py - edit the script, not this file")\n\t)\n'
               f"\t(lib_symbols\n{libs}\t)\n{body}"
               f'\t(sheet_instances (path "/" (page "1")))\n\t(embedded_fonts no)\n)\n')
        OUT.mkdir(exist_ok=True)
        (OUT / f"{PROJECT}.kicad_sch").write_text(sch)
        pro = OUT / f"{PROJECT}.kicad_pro"
        if not pro.exists():
            pro.write_text('{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 3\n  }\n}\n' % PROJECT)


# ================================================================ the circuit
s = Sch()
NPN, PNP = "BCM847DS", "BCM857DS"
XL, XR, M1, M2 = 150, 200, 172, 178          # input column, output column, cross-coupling risers
TOP, BOT, MID = 40, 120, 80                  # rails and the signal (virtual-earth) level

# ---- gain cell: input (log) column
a, b = s.r("R6", "1R8", XL, 46)                                   # RC3
q7 = s.q("Q4", 1, "NPN", NPN, XL, 58, base="R")                   # sim Q7
q3 = s.q("Q2", 1, "PNP", PNP, XL, 70, base="L", e_up=True)        # sim Q3
q1 = s.q("Q1", 1, "NPN", NPN, XL, 90, base="L")                   # sim Q1
q5 = s.q("Q3", 1, "PNP", PNP, XL, 102, base="R", e_up=True)       # sim Q5
c_, d = s.r("R4", "1R8", XL, 114)                                 # RC1
s.wire((XL, TOP), a); s.wire(b, q7["C"]); s.wire(q7["E"], q3["E"])
s.wire(q3["C"], q1["C"]); s.wire(q1["E"], q5["E"]); s.wire(q5["C"], c_); s.wire(d, (XL, BOT))

# ---- gain cell: output (antilog) column
a, b = s.r("R7", "1R8", XR, 46)                                   # RC4
q8 = s.q("Q4", 2, "NPN", NPN, XR, 58, base="L")                   # sim Q8
q4 = s.q("Q2", 2, "PNP", PNP, XR, 70, base="R", e_up=True)        # sim Q4
q2 = s.q("Q1", 2, "NPN", NPN, XR, 90, base="R")                   # sim Q2
q6 = s.q("Q3", 2, "PNP", PNP, XR, 102, base="L", e_up=True)       # sim Q6
c_, d = s.r("R5", "1R8", XR, 114)                                 # RC2
s.wire((XR, TOP), a); s.wire(b, q8["C"]); s.wire(q8["E"], q4["E"])
s.wire(q4["C"], q2["C"]); s.wire(q2["E"], q6["E"]); s.wire(q6["C"], c_); s.wire(d, (XR, BOT))

# ---- cross-coupled bases of the correction pairs
s.wire(q7["B"], (M1, 58), (M1, 52), (XR, 52))                     # Q7 base -> c8
s.wire(q8["B"], (M2, 58), (M2, 50), (XL, 50))                     # Q8 base -> c7
s.wire(q5["B"], (M1, 102), (M1, 108), (XR, 108))                  # Q5 base -> c6
s.wire(q6["B"], (M2, 102), (M2, 110), (XL, 110))                  # Q6 base -> c5

# ---- control-port connections of the log/antilog bases
for qq, name, dx, just in ((q3, "B3", -5, "left bottom"), (q1, "EC-", -5, "left bottom"),
                           (q4, "EC-", 5, "right bottom"), (q2, "SYM", 5, "right bottom")):
    end = (qq["B"][0] + dx, qq["B"][1])
    s.wire(qq["B"], end)
    s.label(name, end, 0, just)

# ---- input amplifier
OPA_FP = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
u1a = s.place("Amplifier_Operational:OPA1678", "U1", "OPA1678", 120, 56, mirror="x", unit=1, fp=OPA_FP,
              ref_at=(2.5, -5.5, "left"), val_at=(2.5, 5.5, "left"))
a, b = s.r("R3", "1k", 134, 47)                                   # RDRV
s.wire(u1a["1"], (134, 56), b); s.wire(a, (134, TOP))
ca, cb = s.c("C1", "22p", 120, 44, horiz=True)                    # CC
s.wire(cb, (128, 44), (128, 56))
s.wire(ca, (108, 44), (108, MID))
s.wire(u1a["2"], (108, u1a["2"][1]))
s.wire(u1a["3"], (112, u1a["3"][1]), (112, 62)); s.power("GND", (112, 62))
s.wire((96, MID), (XL, MID)); s.label("IN", (96, MID))            # host supplies the input resistor

# ---- rails
s.wire((134, TOP), (252, TOP)); s.label("TOP", (158, TOP))
s.wire((XL, BOT), (258, BOT)); s.label("BOT", (158, BOT))

# ---- bias generator (floating shunt regulator between TOP and BOT)
XS, XQ, XP = 226, 240, 252
d1 = s.q("Q5", 1, "PNP", PNP, XS, 50, base="L", e_up=True)        # sim D1
d2 = s.q("Q5", 2, "PNP", PNP, XS, 62, base="L", e_up=True)        # sim D2
d3 = s.q("Q6", 1, "NPN", NPN, XS, 92, base="L")                   # sim D3
qs = s.q("Q6", 2, "NPN", NPN, XQ, 100, base="L")                  # sim QS
qp = s.q("Q7", 0, "PNP", "BC857B", XP, 70, base="L", e_up=True)   # sim QP
s.wire((XS, TOP), d1["E"]); s.wire(d1["C"], d2["E"]); s.wire(d2["C"], d3["C"])
s.wire(d1["B"], (d1["B"][0], d1["C"][1]), d1["C"])
s.wire(d2["B"], (d2["B"][0], d2["C"][1]), d2["C"])
s.wire(d3["B"], (d3["B"][0], d3["C"][1]), d3["C"])
a, b = s.r("R8", "27k", XS, 109)                                  # RSTR
s.wire(d3["E"], a); s.wire(b, (XS, BOT))
s.wire((XS, 100), qs["B"])
s.wire(qs["E"], (XQ, BOT))
a, b = s.r("R9", "30k", XQ, 50)                                   # RPB
s.wire((XQ, TOP), a); s.wire(b, qs["C"])
s.wire((XQ, 70), qp["B"])
s.wire((XP, TOP), qp["E"]); s.wire(qp["C"], (XP, BOT))
a, b = s.r("R10", "6k8", 258, 127)                                # RSINK
s.wire((258, BOT), a); s.wire(b, (258, 134)); s.label("V-", (258, 134), 270, "right bottom")

# ---- output: a current, into the host's current-to-voltage converter (as with a 2181)
s.wire((XR, MID), (272, MID)); s.label("OUT", (272, MID))

# ---- unused half of the dual op-amp, parked as a grounded follower
u1b = s.place("Amplifier_Operational:OPA1678", "U1", "OPA1678", 250, 190, mirror="x", unit=2, fp=OPA_FP,
              ref_at=(2.5, -5.5, "left"), val_at=(2.5, 5.5, "left"))
s.wire(u1b["6"], (u1b["6"][0], 183), (258, 183), (258, 190), u1b["7"])
s.wire(u1b["5"], (242, u1b["5"][1]), (242, 196)); s.power("GND", (242, 196))

# ---- trim network
YT = 162
POT_FP = "Potentiometer_SMD:Potentiometer_Bourns_TC33X_Vertical"
rv1 = s.place("Device:R_Potentiometer_Trim", "RV1", "50k", 120, YT, fp=POT_FP,
              ref_at=(-3, -1.3, "right"), val_at=(-3, 1.3, "right"))
s.wire(rv1["1"], (120, YT - 6)); s.power("+15V", (120, YT - 6))
s.wire(rv1["3"], (120, YT + 6)); s.power("-15V", (120, YT + 6), rot=180)
ra, rb = s.r("R11", "68k", 132, YT, horiz=True)                   # Rsym
s.wire(rv1["2"], ra)
r1a, r1b = s.r("R12", "27R", 160, YT, horiz=True)                 # sim R1
r3a, r3b = s.r("R13", "27R", 180, YT, horiz=True)                 # sim R3
s.wire(rb, r1a); s.label("SYM", (139, YT))
s.wire(r1b, r3a)
s.wire((170, YT), (170, YT - 12), (86, YT - 12)); s.label("EC+", (86, YT - 12))
s.wire(r3b, (194, YT)); s.label("B3", (194, YT), 0, "right bottom")
rv2 = s.place("Device:R_Potentiometer_Trim", "RV2", "50k", 170, YT + 10, rot=270, mirror="y", fp=POT_FP,
              ref_at=(0, -6.6, "center"), val_at=(0, -4.2, "center"))
s.wire((150, YT), (150, YT + 10), min(rv2["1"], rv2["3"]))
s.wire((190, YT), (190, YT + 10), max(rv2["1"], rv2["3"]))
a, b = s.r("R14", "5k6", 170, YT + 18)                            # Rslope
s.wire(rv2["2"], a); s.power("GND", b)
rv3 = s.place("Device:R_Potentiometer_Trim", "RV3", "50k", 220, YT, fp=POT_FP,
              ref_at=(-3, -1.3, "right"), val_at=(-3, 1.3, "right"))
s.wire(rv3["1"], (220, YT - 6)); s.power("+15V", (220, YT - 6))
s.wire(rv3["3"], (220, YT + 6)); s.power("-15V", (220, YT + 6), rot=180)
ra, rb = s.r("R15", "68k", 232, YT, horiz=True)                   # Rgain
s.wire(rv3["2"], ra)
a, b = s.r("R16", "10R", 242, YT + 6)                             # Rg1
s.wire(rb, (248, YT)); s.wire((242, YT), a); s.power("GND", b)
s.label("EC-", (248, YT), 0, "right bottom")
s.text("SYMMETRY", 112, YT - 17, bold=True)
s.text("SLOPE SYMMETRY", 178, YT + 17, bold=True)
s.text("GAIN (0 dB)", 212, YT - 14, bold=True)

# ---- op-amp supply and decoupling
u1c = s.place("Amplifier_Operational:OPA1678", "U1", "OPA1678", 294, 172, unit=3, fp=OPA_FP,
              ref_at=(3, -1.3, "left"), val_at=(3, 1.3, "left"))
vp, vn = u1c["8"], u1c["4"]
a, b = s.c("C3", "100n", 280, 167)
c_, d = s.c("C4", "100n", 280, 177)
s.wire(vp, (vp[0], 162)); s.wire(a, (280, 162), (vp[0], 162)); s.power("+15V", (vp[0], 162))
s.wire(vn, (vn[0], 182)); s.wire(d, (280, 182), (vn[0], 182)); s.power("-15V", (vn[0], 182), rot=180)
s.wire(b, c_); s.wire((280, 172), (273, 172)); s.power("GND", (273, 172))
s.flag((286, 162)); s.flag((286, 182)); s.flag((276, 172))

# ---- module pins: same order and pitch as the THAT 2181 SIP-8
j1 = s.place("Connector_Generic:Conn_01x08", "J1", "2181 SIP-8", 40, 176, mirror="y",
             fp="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
             ref_at=(0, -12.5, "center"), val_at=(0, 12.8, "center"))
for num, net in (("1", "IN"), ("2", "EC+"), ("3", "EC-"), ("4", "SYM"), ("5", "V-"), ("8", "OUT")):
    s.wire(j1[num], (50, j1[num][1])); s.label(net, (50, j1[num][1]))
s.wire(j1["6"], (60, j1["6"][1])); s.power("GND", (60, j1["6"][1]))
s.wire(j1["7"], (66, j1["7"][1])); s.power("+15V", (66, j1["7"][1]))
# the op-amp and trimmers need the real negative rail, which a 2181 socket does not carry
j2 = s.place("Connector_Generic:Conn_01x01", "J2", "VEE (-15V)", 40, 200, mirror="y",
             fp="Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical",
             ref_at=(0, -3.2, "center"), val_at=(0, 3.4, "center"))
s.wire(j2["1"], (54, 200), (54, 202)); s.power("-15V", (54, 202), rot=180)
jp = s.place("Jumper:SolderJumper_2_Open", "JP1", "V- = VEE", 100, 200,
             fp="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
             ref_at=(0, -3.4, "center"), val_at=(0, 3.4, "center"))
s.wire(jp["1"], (92, 200)); s.label("V-", (92, 200), 0, "left bottom")
s.wire(jp["2"], (108, 200), (108, 202)); s.power("-15V", (108, 202), rot=180)

# ---- test points
for i, net in enumerate(("TOP", "BOT", "EC+", "SYM", "GND")):
    x = 190 + 9 * i
    s.place("Connector:TestPoint", f"TP{i + 1}", net, x, 196, fp="TestPoint:TestPoint_Pad_D1.5mm",
            ref_at=(0, -5.2, "center"), show_val=False)
    s.wire((x, 196), (x, 200))
    if net == "GND":
        s.power("GND", (x, 200))
    else:
        s.label(net, (x, 200), 270, "right bottom")

# ---- notes
s.text("Discrete Blackmer VCA - 8-transistor log/antilog gain cell (after Hebert, AES preprint 4055, Fig. 4)",
       28, 16, size=2.0, bold=True)
s.text("Gain = 0 dB at EC+ = 0 V;  control law about +5.9 mV/dB at EC+ (positive voltage increases gain), "
       "drive EC+ from a low-impedance source.\n"
       "Pin-compatible with the THAT 2181 (SIP-8): current in at IN (virtual earth), current out at OUT; "
       "the host supplies the input resistor and I-V converter.\n"
       "Core idle current about 20 uA, set by the bias generator;  R10 sets the standing current (about 2 mA).",
       28, 21)
s.text("INPUT AMPLIFIER", 104, 34, bold=True)
s.text("GAIN CELL", 168, 34, bold=True)
s.text("BIAS GENERATOR", 222, 34, bold=True)
s.text("Matched pairs (one SOT-457 package each)  /  name in the SPICE model\n"
       "Q1A, Q1B  BCM847DS  log / antilog NPN       Q1, Q2\n"
       "Q2A, Q2B  BCM857DS  log / antilog PNP       Q3, Q4\n"
       "Q3A, Q3B  BCM857DS  lower correction pair   Q5, Q6\n"
       "Q4A, Q4B  BCM847DS  upper correction pair   Q7, Q8\n"
       "Q5A, Q5B  BCM857DS  bias string             D1, D2\n"
       "Q6A, Q6B  BCM847DS  bias string / shunt     D3, QS\n"
       "Q7       BC857B    bias shunt              QP",
       28, 34)
s.text("Trim procedure (1 kHz, measure THD at the host output)\n"
       "1. RV1: 0 dB gain, 1 Vrms in - null distortion.\n"
       "2. RV2: -15 dB gain, 3 Vrms in - null distortion.\n"
       "3. Repeat 1 and 2 once.\n"
       "4. RV3: EC+ = 0 V - set unity gain.\n"
       "R3 / C1 set input-amplifier stability and HF distortion.\n"
       "R4-R7 (1R8) cancel transistor bulk resistance.",
       28, 62)
s.text("Using it in a 2181 socket\n"
       "V- (pin 5): the host normally has about 5k1 from this pin to -15 V. Then fit R10 = 0R,\n"
       "  leave JP1 open and bring -15 V to J2 on a wire.\n"
       "  If the host ties pin 5 straight to -15 V instead: fit R10 = 6k8 and close JP1.\n"
       "EC- (pin 3): if the host drives EC-, omit R16, R15 and RV3 (the host sets gain).\n"
       "SYM (pin 4): a host symmetry trim adds to RV1; it is not needed.",
       28, 206)

s.write("Discrete Blackmer VCA - 2181-pinout module", "0.2")
print("wrote", OUT / f"{PROJECT}.kicad_sch")

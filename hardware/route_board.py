#!/usr/bin/env python3
"""First-pass routing of the board written by gen_board.py (a simple two-layer grid router).

    python3 gen_board.py && python3 route_board.py

- Sensitive nets (IN, OUT, then the gain-cell nets) are routed first so they get the shortest paths.
- Tracks prefer the front; the back is kept as free of tracks as possible so its ground pour stays whole.
- The ground pours are cut away (both sides) around the IN and OUT nets to keep stray capacitance
  off the virtual-earth nodes.
The result is meant to be reviewed and improved by hand in KiCad, not treated as final.
"""
import heapq
import math
import sys
from array import array
from pathlib import Path

import pcbnew

PCB = Path(__file__).parent / "blackmer_vca" / "blackmer_vca.kicad_pcb"
G = 0.1                      # grid (mm)
TRACK, VIA_D, VIA_DRILL = 0.25, 0.6, 0.3
PAD_HALO = 0.35              # clearance 0.2 + half track 0.125, rounded up
TRACK_R, VIA_R, VIA_CHECK = 5, 7, 2      # grid cells: track-to-track 0.5 mm, via halo 0.7 mm
EDGE = 0.7
COST_ORTH, COST_DIAG, COST_VIA, BACK_FACTOR = 10, 14, 400, 2.0
CUTOUT_NETS = ("/IN", "/OUT")
CUTOUT_MARGIN = 1.0
FIRST = ["/IN", "/OUT"]
LAST = ["/B3", "/SYM", "/EC-", "/EC+", "/TOP", "/BOT", "/V-", "+15V", "-15V", "GND"]

board = pcbnew.LoadBoard(str(PCB))
if any(True for _ in board.GetTracks()):
    sys.exit("board already has tracks - run gen_board.py first (this would discard manual work)")
bb = board.GetBoardEdgesBoundingBox()
LW = 0.1                                             # outline line width, included in the bounding box
X0, Y0 = pcbnew.ToMM(bb.GetX()) + LW / 2, pcbnew.ToMM(bb.GetY()) + LW / 2
NX = int(round((pcbnew.ToMM(bb.GetWidth()) - LW) / G)) + 1
NY = int(round((pcbnew.ToMM(bb.GetHeight()) - LW) / G)) + 1
N = NX * NY
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

own = [array("i", [0]) * N, array("i", [0]) * N]     # 0 free, >0 reserved for that net, -1 blocked
thpad = array("i", [0]) * N                          # net of the through-hole pad covering this node
inpad = bytearray(N)                                 # node lies on/near any pad (no vias here)
near = [array("i", [0]) * N, array("i", [0]) * N]    # like `own` but 1 mm around pads: costly for other nets
NEAR, NEAR_COST = 1.2, 40


def mark(layer, i, net):
    cur = own[layer][i]
    if cur == 0:
        own[layer][i] = net
    elif cur != net:
        own[layer][i] = -1


def disc(r):
    return [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if dx * dx + dy * dy <= r * r]


DISC_T, DISC_V, DISC_C = disc(TRACK_R), disc(VIA_R), disc(VIA_CHECK)


def nodes_in(x1, y1, x2, y2):
    ix1, ix2 = max(0, math.ceil((x1 - X0) / G - 1e-9)), min(NX - 1, math.floor((x2 - X0) / G + 1e-9))
    iy1, iy2 = max(0, math.ceil((y1 - Y0) / G - 1e-9)), min(NY - 1, math.floor((y2 - Y0) / G + 1e-9))
    return [iy * NX + ix for iy in range(iy1, iy2 + 1) for ix in range(ix1, ix2 + 1)]


# ---- board edge
e = int(round(EDGE / G))
for iy in range(NY):
    for ix in range(NX):
        if ix < e or iy < e or ix > NX - 1 - e or iy > NY - 1 - e:
            own[0][iy * NX + ix] = own[1][iy * NX + ix] = -1

# ---- pads
netpads = {}           # net code -> list of (centre, {states})
stubs = []
STUB = 1.2
names = {}
unnamed = 100000
for fp in board.GetFootprints():
    for pad in fp.Pads():
        r = pad.GetBoundingBox()
        x1, y1 = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
        x2, y2 = x1 + pcbnew.ToMM(r.GetWidth()), y1 + pcbnew.ToMM(r.GetHeight())
        code = pad.GetNetCode()
        if code <= 0:
            unnamed += 1
            code = unnamed
        names[code] = pad.GetNetname()
        layers = [k for k, L in enumerate(LAYERS) if pad.IsOnLayer(L)]
        for k in layers:
            for i in nodes_in(x1 - PAD_HALO, y1 - PAD_HALO, x2 + PAD_HALO, y2 + PAD_HALO):
                mark(k, i, code)
        for i in nodes_in(x1 - 0.45, y1 - 0.45, x2 + 0.45, y2 + 0.45):
            inpad[i] = 1
        for k in layers:
            for i in nodes_in(x1 - NEAR, y1 - NEAR, x2 + NEAR, y2 + NEAR):
                near[k][i] = code if near[k][i] in (0, code) else -1
        inner = nodes_in(x1 + 0.1, y1 + 0.1, x2 - 0.1, y2 - 0.1)
        if len(layers) == 2:
            for i in inner:
                thpad[i] = code
        c = pad.GetPosition()
        states = {(k, i) for k in layers for i in inner}
        netpads.setdefault(code, []).append(((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)), states))
        # fan-out: a short stub straight out of every transistor / op-amp pad, laid before any routing,
        # so a neighbour's track can never box a pad in
        ref = fp.GetReference()
        if ref[0] in "QU" and len(layers) == 1 and (x2 - x1) > (y2 - y1):
            sign = 1 if c.x > fp.GetPosition().x else -1
            iy = int(round((pcbnew.ToMM(c.y) - Y0) / G))
            xa = pcbnew.ToMM(c.x)
            xb = (x2 if sign > 0 else x1) + sign * STUB
            ia, ib = sorted((int(round((xa - X0) / G)), int(round((xb - X0) / G))))
            path = [(0, iy * NX + ix) for ix in range(ia, ib + 1)]
            stubs.append((path if sign > 0 else path[::-1], code, states, set(path) - states))
            states |= set(path)

MOVES = [(1, 0, COST_ORTH), (-1, 0, COST_ORTH), (0, 1, COST_ORTH), (0, -1, COST_ORTH),
         (1, 1, COST_DIAG), (1, -1, COST_DIAG), (-1, 1, COST_DIAG), (-1, -1, COST_DIAG)]


def via_ok(i, net):
    if inpad[i]:
        return False
    ix, iy = i % NX, i // NX
    for dx, dy in DISC_C:
        j = (iy + dy) * NX + ix + dx
        for k in (0, 1):
            v = own[k][j]
            if v != 0 and v != net:
                return False
    return True


def route(net, sources, targets, tc):
    """A* from the set of states `sources` to any state in `targets`; returns the state path."""
    tx, ty = (tc[0] - X0) / G, (tc[1] - Y0) / G
    best, parent, heap = {}, {}, []

    def h(i):
        dx, dy = abs(i % NX - tx), abs(i // NX - ty)
        return int(COST_ORTH * max(dx, dy) + (COST_DIAG - COST_ORTH) * min(dx, dy))

    for s in sources:
        if own[s[0]][s[1]] in (0, net):
            best[s] = 0
            heapq.heappush(heap, (h(s[1]), 0, s))
    while heap:
        f, g, s = heapq.heappop(heap)
        if g > best.get(s, 1 << 60):
            continue
        if s in targets:
            path = [s]
            while s in parent:
                s = parent[s]
                path.append(s)
            return path[::-1]
        k, i = s
        ix, iy = i % NX, i // NX
        o = own[k]
        nr = near[k]
        for dx, dy, c in MOVES:
            j = i + dy * NX + dx
            v = o[j]
            if v != 0 and v != net:
                continue
            if dx and dy:                                   # no squeezing diagonally past a corner
                a, b = o[i + dx], o[i + dy * NX]
                if (a != 0 and a != net) or (b != 0 and b != net):
                    continue
            ng = g + (c if k == 0 else int(c * BACK_FACTOR))
            if nr[j] != 0 and nr[j] != net:                 # keep clear of other nets' pads: leaves escape room
                ng += NEAR_COST
            t = (k, j)
            if ng < best.get(t, 1 << 60):
                best[t] = ng
                parent[t] = s
                heapq.heappush(heap, (ng + h(j), ng, t))
        t = (1 - k, i)                                      # change layer
        v = own[1 - k][i]
        if v == 0 or v == net:
            cost = 0 if thpad[i] == net else (COST_VIA if via_ok(i, net) else None)
            if cost is not None and g + cost < best.get(t, 1 << 60):
                best[t] = g + cost
                parent[t] = s
                heapq.heappush(heap, (g + cost + h(i), g + cost, t))
    return None


def pt(i):
    return pcbnew.VECTOR2I(pcbnew.FromMM(X0 + (i % NX) * G), pcbnew.FromMM(Y0 + (i // NX) * G))


def commit(path, code):
    run = [path[0]]
    for prev, cur in zip(path, path[1:] + [None]):
        if cur is not None and cur[0] == prev[0]:
            run.append(cur)
            continue
        # emit the run on one layer, merging collinear steps
        k = run[0][0]
        pts, last = [run[0][1]], None
        for a, b in zip(run, run[1:]):
            d = (b[1] % NX - a[1] % NX, b[1] // NX - a[1] // NX)
            if d == last:
                pts[-1] = b[1]
            else:
                pts.append(b[1])
            last = d
        for a, b in zip(pts, pts[1:]):
            segs.append((a, b, k, code))
        for _, i in run:
            ix, iy = i % NX, i // NX
            for dx, dy in DISC_T:
                if 0 <= ix + dx < NX and 0 <= iy + dy < NY:
                    mark(k, (iy + dy) * NX + ix + dx, code)
        if cur is not None:
            i = cur[1]
            if thpad[i] != code:
                vias.append((i, code))
                ix, iy = i % NX, i // NX
                for dx, dy in DISC_V:
                    if 0 <= ix + dx < NX and 0 <= iy + dy < NY:
                        mark(0, (iy + dy) * NX + ix + dx, code)
                        mark(1, (iy + dy) * NX + ix + dx, code)
            run = [cur]


# ---- net order: IN, OUT, local gain-cell nets (shortest first), then control, rails, ground
def span(code):
    xs = [c[0] for c, _ in netpads[code]]
    ys = [c[1] for c, _ in netpads[code]]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


codes = [c for c in netpads if len(netpads[c]) > 1]
by_name = {names[c]: c for c in codes}
middle = sorted((c for c in codes if names[c] not in FIRST + LAST), key=span)
first = [by_name[n] for n in FIRST if n in by_name]
rest = middle + [by_name[n] for n in LAST if n in by_name]
base_own = [array("i", o) for o in own]
priority = []
for attempt in range(1, 9):
    # nets that could not be completed are routed earlier on the next attempt
    own = [array("i", o) for o in base_own]
    segs, vias, failed = [], [], []
    used, laid = {}, []
    for path, code, states, extra in stubs:
        if not all(own[k][i] in (0, code) for k, i in path):
            states -= extra                    # no room for this stub: the pad is just the pad
        else:
            n = len(segs)
            commit(path, code)
            del segs[n:]                       # drawn later, trimmed to the part actually used
            laid.append((path, code))
    order = first + priority + [c for c in rest if c not in priority]
    for code in order:
        pads = netpads[code]
        tree = set(pads[0][1])
        centres = [pads[0][0]]
        todo = pads[1:]
        while todo:
            nxt = min(todo, key=lambda p: min(math.dist(p[0], c) for c in centres))
            todo.remove(nxt)
            path = route(code, tree, nxt[1], nxt[0])
            if path is None:
                failed.append(code)
                continue
            commit(path, code)
            used.setdefault(code, set()).update(path)
            tree |= set(path) | nxt[1]
            centres.append(nxt[0])
    print(f"attempt {attempt}: {len(failed)} connections failed", sorted({names[c] for c in failed}))
    if not failed:
        break
    priority = list(dict.fromkeys(failed)) + [c for c in priority if c not in failed]
failed = sorted({names[c] for c in failed})

for path, code in laid:                        # keep each fan-out stub only as far as a route uses it
    far = max((n for n, q in enumerate(path) if q in used.get(code, ())), default=0)
    if far:
        segs.append((path[0][1], path[far][1], 0, code))
for a, b, k, code in segs:
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pt(a)); t.SetEnd(pt(b))
    t.SetWidth(pcbnew.FromMM(TRACK)); t.SetLayer(LAYERS[k]); t.SetNet(board.FindNet(code))
    board.Add(t)
for i, code in vias:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(i)); v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(VIA_D))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL)); v.SetNet(board.FindNet(code))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(v)

# ---- pour cut-outs around the virtual-earth nets
def rect(ps, x1, y1, x2, y2):
    r = pcbnew.SHAPE_POLY_SET()
    r.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        r.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    ps.BooleanAdd(r)


for name in CUTOUT_NETS:
    ps = pcbnew.SHAPE_POLY_SET()
    m = CUTOUT_MARGIN
    for t in board.GetTracks():
        if t.GetNetname() == name:
            a, b = t.GetStart(), t.GetEnd()
            ax, ay, bx, by = (pcbnew.ToMM(v) for v in (a.x, a.y, b.x, b.y))
            steps = max(1, int(math.dist((ax, ay), (bx, by)) / 0.4))      # follow diagonals closely
            for n in range(steps + 1):
                x, y = ax + (bx - ax) * n / steps, ay + (by - ay) * n / steps
                rect(ps, x - m, y - m, x + m, y + m)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == name:
                r = pad.GetBoundingBox()
                x, y = pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY())
                rect(ps, x - 0.6, y - 0.6, x + pcbnew.ToMM(r.GetWidth()) + 0.6, y + pcbnew.ToMM(r.GetHeight()) + 0.6)
    ps.Simplify()
    for n in range(ps.OutlineCount()):
        ol = ps.Outline(n)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetZoneName(f"no pour under {name.strip('/')}")
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False); z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
        o = z.Outline()
        o.NewOutline()
        for j in range(ol.PointCount()):
            p = ol.CPoint(j)
            o.Append(p.x, p.y)
        board.Add(z)

pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(str(PCB), board)
tracks = [t for t in board.GetTracks()]
nvia = sum(1 for t in tracks if t.Type() == pcbnew.PCB_VIA_T)
back = sum(t.GetLength() for t in tracks if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == pcbnew.B_Cu)
total = sum(t.GetLength() for t in tracks if t.Type() != pcbnew.PCB_VIA_T)
for name in CUTOUT_NETS:
    L = sum(t.GetLength() for t in tracks if t.GetNetname() == name and t.Type() != pcbnew.PCB_VIA_T)
    print(f"{name}: {pcbnew.ToMM(L):.1f} mm of track")
print(f"routed {len(order)} nets: {len(tracks) - nvia} segments, {nvia} vias, "
      f"{pcbnew.ToMM(total):.0f} mm of track ({pcbnew.ToMM(back):.0f} mm on the back)")
print("FAILED connections on nets:", failed if failed else "none")

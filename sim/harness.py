"""ngspice batch harness for the Blackmer VCA study.

Circuit libraries in sim/lib are simulator-portable; this harness generates
ngspice testbenches (using .control blocks), runs them and returns numpy arrays.
"""
import subprocess, tempfile, os, pathlib
import numpy as np
from scipy.interpolate import CubicSpline

LIB = pathlib.Path(__file__).resolve().parent / "lib"
OPTS = ".options reltol=1e-6 abstol=1e-13 vntol=1e-8 method=gear"


def run(netlist: str, outputs: dict, keep=False):
    """Run a netlist. `outputs` maps name -> file written by wrdata. Returns name -> 2D array."""
    d = tempfile.mkdtemp(prefix="bvca_")
    cir = os.path.join(d, "tb.cir")
    for k, v in outputs.items():
        netlist = netlist.replace("{" + k + "}", os.path.join(d, v))
    open(cir, "w").write(netlist)
    open(os.path.join(d, ".spiceinit"), "w").write("set ngbehavior=psa\n")   # vendor op-amp models are PSpice syntax
    p = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, cwd=d)
    res = {}
    for k, v in outputs.items():
        f = os.path.join(d, v)
        if not os.path.exists(f):
            raise RuntimeError(f"ngspice produced no {v}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
        res[k] = np.loadtxt(f)
    res["_log"] = p.stdout + p.stderr
    if not keep:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        os.rmdir(d)
    return res


MODELS = LIB.parent.parent / "models"
OPAMPS = {   # name -> (library file, subcircuit name); pins are IN+ IN- VCC VEE OUT for all of these
    "OPA1678": ("opamps/OPA167x.LIB", "OPA167x"),
    "OPA1656": ("opamps/OPA1656.LIB", "OPA1656"),
    "OPA1612": ("opamps/OPA161x.LIB", "OPA161x"),
    "TL072": ("opamps/TL072.lib", "TL072"),
}


def _oa_wrapper(name, opamp):
    if opamp == "ideal":
        return f".subckt {name} inp inn vcc vee out\nX1 inp inn out OPAMP_IDEAL\n.ends\n"
    return f".subckt {name} inp inn vcc vee out\nX1 inp inn vcc vee out {OPAMPS[opamp][1]}\n.ends\n"


def header(core_models="bjt_ideal.lib", temp=27, extra="", oa_in="ideal", oa_out="ideal"):
    """Common preamble. `core_models` must define QNCORE/QPCORE. oa_in / oa_out pick the
    input-amplifier and output I-V op-amps ("ideal" or a key of OPAMPS)."""
    incs = "".join(f".include {MODELS}/{OPAMPS[o][0]}\n" for o in sorted({oa_in, oa_out} - {"ideal"}))
    return f"""* generated testbench
.include {LIB}/opamp_ideal.lib
{incs}{_oa_wrapper("OA_IN", oa_in)}{_oa_wrapper("OA_OUT", oa_out)}.include {LIB}/{core_models}
.include {LIB}/blackmer4.lib
.include {LIB}/blackmer8.lib
.include {LIB}/blackmer8d.lib
{OPTS}
.temp {temp}
{extra}
"""


def vca_fixture(core="BLACKMER8", core_params="", sym=0.5, gain=0.5, slope=0.5, rin=20e3, rf=20e3, cf="22p",
                r1=27, rsym=68e3, rg1=10, rgain=68e3, rslope=5.6e3, rpot=50e3, vs=15):
    """2181-style fixture with three trimmer pots (position 0..1, 0.5 = centre).

    SYM   : pot across +/-vs -> rsym -> `sym` (Q2 base); r1 from sym to the control node `ecp`
            (Hebert Fig. 9). Cancels net Vbe mismatch between the two signal polarities.
    SLOPE : pot between `sym` and `b3` (Q3 base), wiper -> rslope -> ground; r1 from b3 to `ecp`.
            Attenuates the control voltage very slightly more on one polarity than the other,
            cancelling a control-slope difference between the NPN-primary and PNP-primary halves.
    GAIN  : pot across +/-vs -> rgain -> `ecn`; rg1 from ecn to ground. Sets 0 dB at Ec = 0.
    The gain-control voltage is applied to node `ecp` by the testbench.
    """
    def pot(name, pos, top, wiper, bottom):
        pos = min(max(pos, 1e-6), 1 - 1e-6)
        return (f"R{name}a {top} {wiper} {rpot * (1 - pos)}\n"
                f"R{name}b {wiper} {bottom} {rpot * pos}\n")
    return (f"Vpos vpos 0 {vs}\nVneg vneg 0 {-vs}\n"
            + pot("ps", sym, "vpos", "ws", "vneg") + f"Rsym ws sym {rsym}\nR1 sym ecp {r1}\nR3 b3 ecp {r1}\n"
            + pot("pl", slope, "sym", "wl", "b3") + f"Rslope wl 0 {rslope}\n"
            + pot("pg", gain, "vpos", "wg", "vneg") + f"Rgain wg ecn {rgain}\nRg1 ecn 0 {rg1}\n"
            + f"Rin vin in {rin}\n"
            + f"X1 in out b3 ecn sym {'vpos vneg ' if core.endswith('D') else ''}{core} {core_params}\n"
            + f"XO2 0 out vpos vneg vo OA_OUT\nRf vo out {rf}\nCf vo out {cf}\n")


def harmonics(t, v, f0, ncycles, nharm=9):
    """Resample the last `ncycles` of v(t) coherently; return (fund_amp, [h2..], thd)."""
    T = ncycles / f0
    t0 = t[-1] - T
    N = 4096 * ncycles
    tu = t0 + np.arange(N) * T / N
    # drop duplicate timepoints
    keep = np.concatenate(([True], np.diff(t) > 0))
    vu = CubicSpline(t[keep], v[keep])(tu)
    X = np.fft.rfft(vu) / (N / 2)
    a = np.abs(X)
    fund = a[ncycles]
    h = np.array([a[ncycles * k] for k in range(2, nharm + 1)])
    return fund, h, float(np.sqrt(np.sum(h ** 2)) / fund)


def thd_run(amp, ec, f0=1e3, hdr=None, fixture=None, settle=10, ncyc=8, ppc=2000, extra="", full=False):
    hdr = hdr or header()
    fixture = fixture or vca_fixture()
    tstep = 1 / (f0 * ppc)
    tstop = (settle + ncyc) / f0
    net = f"""{hdr}
Vin vin 0 SIN(0 {amp} {f0})
Vecp ecp 0 {ec}
{fixture}
{extra}
.control
tran {tstep} {tstop} {(settle - 1) / f0} {tstep}
wrdata {{out}} v(vo)
.endc
.end
"""
    r = run(net, {"out": "out.txt"})
    t, v = r["out"][:, 0], r["out"][:, 1]
    f, h, thd = harmonics(t, v, f0, ncyc)
    if full:
        return f, h, thd, float(np.mean(v[t > t[-1] - ncyc / f0]))
    return f, h, thd


def ac_peaking(vdc, ec, hdr, fixture):
    """Closed-loop small-signal response of the input-amplifier loop (Vin -> op-amp output),
    linearised at a DC input level. (The I-V stage's Cf would hide this at Vo.)
    Returns (peaking in dB above the 1 kHz value, frequency of the peak, -3 dB bandwidth).
    Peaking of more than a few dB means the input-amplifier loop is short of phase margin
    at that instantaneous signal current."""
    hdr = hdr.replace(OPTS, ".options method=gear")     # tight tolerances break the vendor op-amp DC solve
    net = f"""{hdr}
Vin vin 0 dc {vdc} ac 1
Vecp ecp 0 {ec}
{fixture}
.control
ac dec 50 1k 300meg
wrdata {{out}} vdb(x1.oa)
.endc
.end
"""
    r = run(net, {"out": "o.txt"})["out"]
    f, g = r[:, 0], r[:, 1] - r[0, 1]
    i = int(np.argmax(g))
    below = np.where(g < -3)[0]
    return float(g[i]), float(f[i]), float(f[below[0]]) if len(below) else float("nan")

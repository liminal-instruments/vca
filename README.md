# Discrete Blackmer VCA

An open, low-cost voltage-controlled amplifier built from discrete matched transistor pairs, intended
as a replacement for the THAT 2180/2181 after THAT Corporation's September 2026 end-of-life notice.

**Status: simulation and schematic only. No hardware has been built or measured yet.**

## Goals

- A modern Blackmer log/antilog gain cell from cheap, available parts (Nexperia BCM847DS / BCM857DS
  matched pairs and one dual op-amp), not an at-any-cost replica.
- Parts cost comparable to a CoolAudio V2181: currently about **£2.04 per channel at 100-off**
  (see `bom/bom_v0.csv`; passives are estimates).
- THD below 0.01 % after trimming. The circuit works untrimmed; calibration improves it.

## The circuit

The 8-transistor gain cell described by Hebert (AES preprint 4055, Fig. 4): a log/antilog quad with
two cross-coupled correction pairs, an op-amp input amplifier, a bias generator built from the same
matched pairs, and an op-amp current-to-voltage output stage. Three trimmers set symmetry, slope
symmetry and unity gain. Control law is about 5.9 mV/dB.

Schematic: [`hardware/blackmer_vca/blackmer_vca.pdf`](hardware/blackmer_vca/blackmer_vca.pdf)

## Simulated performance

ngspice, vendor transistor and OPA1678 models, pairs at datasheet-limit mismatch, 1 kHz, after trim:

| Gain | Input | THD |
|---|---|---|
| -30 dB | 3.16 Vrms | 0.0015 % |
| -15 dB | 3.16 Vrms | 0.0024 % |
| 0 dB | 1 Vrms | 0.0027 % |
| 0 dB | 3.16 Vrms | 0.0085 % |
| +15 dB | 0.56 Vrms | 0.010 % |
| +30 dB | 0.1 Vrms | 0.011 % |

Untrimmed, the same worst-case parts give 0.04-0.18 %. Known limits and open work:

- Distortion rises with frequency (about 0.026 % at 10 kHz untrimmed) because of the input-amplifier
  compensation capacitor.
- The vendor transistor models have no temperature dependence, so trim drift is not yet characterised.
- Noise, Monte Carlo and temperature sweeps have not been run.
- Results are from ngspice only; they have not been cross-checked in LTspice or on a bench.

## Repository layout

| Path | Contents |
|---|---|
| `sim/` | ngspice netlists (`lib/`), Python harness and studies, results |
| `hardware/` | KiCad 9 project, schematic generator and netlist check |
| `bom/` | Bill of materials with 100-off prices |
| `docs/` | Patents, and links to the papers and datasheets used |
| `models/` | Where to put the vendor SPICE models (not redistributed here) |

## Running the simulations

Requires ngspice (45 or later) and Python 3.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# download the vendor models listed in models/README.md
cd sim
../.venv/bin/python study_cells.py           # 4- vs 8-transistor cell, ideal vs real devices
../.venv/bin/python study_trim.py OPA1678    # three-trimmer calibration
../.venv/bin/python study_comp.py OPA1678    # input-amplifier compensation sweep
```

## Regenerating the schematic

Requires KiCad 9 with its standard symbol libraries.

```
cd hardware
python3 gen_schematic.py     # writes blackmer_vca/blackmer_vca.kicad_sch
python3 check_netlist.py     # compares the schematic's netlist with the simulated circuit
```

## Disclaimer

This project is not affiliated with or endorsed by THAT Corporation, CoolAudio or any other
manufacturer. Product names are trademarks of their owners and are used only to identify the parts
discussed. The original Blackmer patents have expired.

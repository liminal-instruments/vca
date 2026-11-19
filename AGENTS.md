# Agent notes

Context for an AI agent (or a new contributor) picking this project up. `README.md` is the
public-facing description; this file records the working state, the conventions and the traps.

## What this is

A discrete-transistor clone of the THAT 2181 Blackmer VCA, started after THAT Corp announced
end-of-life for the 2180/2181 (September 2026). The repository is public on purpose: the aim is
to give the industry a replacement.

Goals, as set by the project owner:

- An alternative to the CoolAudio V2181 at a similar price: about £2 per channel at 100 off
  (hard limit £5).
- THD+N below 0.01 %. Beating the V2181 is a welcome upside, not a requirement.
- Cheap matched pairs (Nexperia BCM847DS / BCM857DS), not MAT14-class parts.
- It must work untrimmed; calibration improves it.
- Same pinout, pin spacing and footprint as the 2181 (SIP-8).
- Calibration by microcontroller and DACs is parked. All trims are trimmer resistors, in the
  model and on the first prototypes.

## State (November 2026)

Nothing has been built or measured. Every performance number in this repository is an ngspice
simulation.

| Area | State |
|---|---|
| Simulation | Buildable 8-transistor cell with OPA1678 simulated, trimmed and untrimmed, at 1 kHz |
| Schematic | rev 0.2, a module with the 2181 pinout; netlist checked against the simulated circuit |
| BOM | `bom/bom_v0.csv`, 28 parts, £2.01 per module |
| PCB | 56 x 38 mm, two layers, script-placed and script-routed first pass; DRC clean; not reviewed by a person |
| Fabrication files | None generated yet |

Next step agreed with the owner: review the layout in KiCad, order boards, build prototypes,
then compare measurements against the simulation.

## Layout of the repository

- `sim/harness.py` - builds ngspice decks, runs them in batch mode, extracts THD and gain.
- `sim/study_cells.py`, `study_trim.py`, `study_comp.py` - the studies behind the README table.
- `sim/lib/` - subcircuits. `blackmer8d.lib` is the buildable cell that the schematic follows.
  `blackmer4.lib` and `blackmer8.lib` are earlier idealised cells.
- `sim/results/trim_opa1678.txt` - the trimmed results quoted in the README.
- `hardware/gen_schematic.py` - writes `blackmer_vca.kicad_sch` and the PDF source.
- `hardware/check_netlist.py` - compares the KiCad netlist with a hand-written expected netlist.
- `hardware/gen_board.py` - places footprints, outline and ground pours. Overwrites the board.
- `hardware/route_board.py` - grid autorouter, pour cut-outs, zone fill.
- `docs/`, `models/` - only the READMEs and the patents are tracked. Papers, datasheets and
  vendor SPICE models are kept locally and ignored by git because they are not redistributable.
  The READMEs link to the sources.

## The circuit in brief

- Core: Blackmer log/antilog cell with eight transistors, after Hebert (AES preprint 4055,
  Fig. 4): two log/antilog pairs plus cross-coupled correction pairs with 1.8 ohm emitter
  resistors (R4-R7).
- Input amplifier: OPA1678 (U1A), 1 k drive resistor (R3), 22 pF compensation (C1). The owner
  has used this part before and wants to keep it. TL072 was tried in simulation and rejected
  (6-37 dB of closed-loop peaking).
- Bias: floating shunt generator (junction string Q5/Q6 plus Sziklai pair with Q7), sink
  resistor R10. Core idle current is about 22 uA in simulation.
- Control law: about +5.9 mV/dB at EC+. Positive EC+ increases gain.
- Trims: RV1 symmetry, RV2 slope symmetry, RV3 gain.
- Current in, current out, like the 2181: the host board supplies the 20 k input resistor and
  the current-to-voltage converter.

Pinout (J1): 1 IN, 2 EC+, 3 EC-, 4 SYM, 5 V-, 6 GND, 7 V+, 8 OUT.

Transistor packages against the SPICE names: Q1 = sim Q1/Q2 (BCM847DS), Q2 = sim Q3/Q4
(BCM857DS), Q3 = sim Q5/Q6 (BCM857DS), Q4 = sim Q7/Q8 (BCM847DS), Q5 = D1/D2 (BCM857DS),
Q6 = D3/QS (BCM847DS), Q7 = QP (BC857B).

### Not a pure drop-in yet

On a real 2181, pin 5 is a current-programming pin fed through about 5.1 k from -15 V. This
module needs a real -15 V rail for the op-amp, so:

- -15 V arrives on a separate pad, J2.
- Host has 5.1 k on pin 5: fit R10 = 0 R, leave JP1 open, wire -15 V to J2.
- Host ties pin 5 straight to -15 V: fit R10 = 6.8 k, close JP1.
- If the host drives EC-, omit R16, R15 and RV3.

The 5.1 k case gives about 2.4 mA where the simulation used 2.05 mA. That case has not been
simulated.

## Simulated performance (trimmed, 1 kHz, datasheet-limit mismatch)

| Gain, level | THD |
|---|---|
| -30 dB, 3.16 V | 0.0015 % |
| -15 dB | 0.0024 % |
| 0 dB, 1 V | 0.0027 % |
| 0 dB, 3.16 V | 0.0085 % |
| +15 dB | 0.010 % |
| +30 dB | 0.011 % |

Untrimmed: 0.04-0.18 %. Gain error within 0.06 dB. Trimmer positions at the optimum: symmetry
0.4524, slope 0.8429, gain 0.6393.

## Known weaknesses and open work

Simulation:

- Only ngspice 45.2 has been used. The owner asked for LTspice; it is not installed, so there
  is no cross-check.
- The vendor transistor models carry no temperature dependence. Temperature, Monte Carlo and
  noise have not been simulated.
- High-frequency distortion from the compensation capacitor: 0.026 % at 10 kHz untrimmed.
- DC output shifts with gain (control feedthrough), -17.7 mV at +30 dB. Not addressed.
- The 2181-host condition (2.4 mA through pin 5) is unsimulated.

Hardware:

- Footprints and pin mappings came from datasheets and KiCad's stock libraries. Check the
  BCM847DS / BCM857DS pin numbering and the TC33X trimmer footprint against real parts before
  ordering.
- The IN net is about 60 mm long. It is the most sensitive node. Moving U1 nearer pin 1 and the
  cell would shorten it.
- The matched-pair block was spread to a 7.5 x 6 mm pitch so the router could reach the centre
  pads. A hand layout should pull the packages closer for thermal matching.
- 71 vias and 263 mm of track on the back break up the back ground pour.
- All tracks are 0.25 mm, supply rails included.
- The unused half of U1 is parked as a grounded follower and wastes supply current. A single
  OPA1677 is a possible substitute.
- EC- has 10 ohms to ground on the module (R16).

Project:

- No licence file. CERN-OHL for hardware plus MIT for scripts was suggested; the owner has not
  decided.

## Working here

Tools:

- ngspice 45.2 in batch mode. Python virtual environment in `.venv` from `requirements.txt`
  (numpy, scipy, matplotlib, spicelib).
- KiCad 9.0.9. `kicad-cli` and the `pcbnew` Python module are used from the system `python3`,
  not the virtual environment.

Commands:

```
cd sim
../.venv/bin/python study_trim.py OPA1678     # trimmed-performance study
../.venv/bin/python study_comp.py OPA1678     # input-amplifier compensation sweep

cd hardware
python3 gen_schematic.py                      # regenerate the schematic
python3 check_netlist.py                      # must print MATCH
python3 gen_board.py                          # OVERWRITES the board
python3 route_board.py                        # refuses if tracks already exist
kicad-cli pcb drc --schematic-parity blackmer_vca/blackmer_vca.kicad_pcb
```

Rules:

- **Do not run `gen_board.py` or `route_board.py` without asking.** Once the board has been
  edited by hand in KiCad, running them destroys that work. Check `git log` and `git diff` on
  the `.kicad_pcb` first.
- The schematic is generated. Change `gen_schematic.py`, not the `.kicad_sch`, unless the owner
  has started editing the schematic by hand. Ask if unsure.
- When the circuit changes, change it in three places and keep them agreeing: `sim/lib/`,
  `gen_schematic.py`, and the `EXPECTED` netlist in `check_netlist.py`. The expected netlist is
  written by hand, independently of the drawing code, so that it is a real check.
- Keep designators in `bom/bom_v0.csv` in step with the schematic.
- Mark every number as simulated or measured. Do not present simulated figures as measured.
- Do not commit papers, datasheets, vendor models, invoices or chat transcripts. Check
  `.gitignore` before adding files under `docs/` or `models/`.
- The owner makes the commits. Stage changes when asked; commit or push only when asked.
- Nexperia, ST, ADI and CoolAudio block scripted downloads. Ask the owner to fetch files from
  those sites.

Traps met so far:

- KiCad schematic files: wires must be split at every connection point; a junction is needed
  where three or more ends meet. KiCad applies rotation before mirroring. The dual-transistor
  symbols live in the `Transistor_BJT` library.
- `kicad-cli sch erc` reports "library not configured" warnings because the command line has no
  symbol library table. These are not circuit errors.
- `pcbnew`: filling zones on a board created in memory crashes. Save, reload with `LoadBoard`,
  then fill. The rule-area call is `SetDoNotAllowCopperPour`.
- The router's success depends on placement and net order. If a placement change leaves nets
  unrouted, the stub length (`STUB`) and the near-pad cost are the settings that mattered.

# Vendor SPICE models

The vendor model files are copyrighted and are not redistributed here. Download them and place
them as below (this folder is git-ignored apart from this file).

| File | Source |
|---|---|
| `BCM847DS.txt`, `BCM857DS.txt` | Nexperia product pages for BCM847DS / BCM857DS, "SPICE model" download |
| `opamps/OPA167x.LIB` | Texas Instruments, https://www.ti.com/lit/zip/SBOMAC3 |
| `opamps/OPA1656.LIB` | Texas Instruments, https://www.ti.com/lit/zip/SBOMAW6 |
| `opamps/OPA161x.LIB` | Texas Instruments, https://www.ti.com/lit/zip/SBOMBM7 |
| `opamps/TL072.lib` | Texas Instruments, https://www.ti.com/lit/zip/SLOJ067 |

Only the op-amp files are read by the simulations. The transistor parameters the simulations use
are in `sim/lib/bjt_bcm.lib`; the Nexperia files are kept for reference.

The TI models are PSpice-syntax; the harness runs ngspice in PSpice-compatibility mode for them.
In ngspice the OPA1656 and OPA161x models give implausible noise results; OPA167x behaves.

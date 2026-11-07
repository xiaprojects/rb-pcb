# RB01HAT Rev A concept board

**This is a visualisation, not the Rev A design. Do not fabricate it.** It shows what the plan in
[docs/06-custom-pcb.md](../../../docs/06-custom-pcb.md) could look like. The Rev 0 bring-up gate in
[hardware/kicad/README.md](../README.md) still applies, and `hardware/*.csv` stays the source of truth.

Everything here is generated. Change `generate.py`, not the KiCad files.

## What it is

- HAT+ outline, 65 x 56.5 mm, four layers: F.Cu signals, In1 GND, In2 3V3, B.Cu signals.
- Parts sit in zones Z1-Z6 of [docs/03-mechanical.md](../../../docs/03-mechanical.md).
- Nets and refdes come from [hardware/netlist.csv](../../netlist.csv). The script stops if any on-board row
  doesn't land on a pad of that net. U9-U12 and J12 are not here: they belong to the extension.
- Fully routed, and the KiCad DRC passes with 0 errors, 0 warnings and 0 unconnected items.
- Chip pinouts were read from the vendor datasheets (listed at `PIN_MAP` in `generate.py`).

A clean DRC proves the copper is consistent with the rules. It doesn't prove the circuit works.

## Renders

In `renders/`, 3840 x 2160 JPG: `-hero` and `-right` (3/4 views), `-top`, `-bottom`.

## Regenerate

```bash
python3 generate.py            # board, routing, DRC
python3 generate.py --preview  # plus 1600 x 900 renders
python3 generate.py --render   # plus 4K renders (several minutes)
```

It needs the system Python with KiCad 9's `pcbnew`, numpy and Pillow, plus a C compiler for `astar.c`. The
`kicad-packages3d` package is not installed here, so the first run downloads the 3D models it needs into
`3dmodels/`.

## Defaults for the open decisions

These are placeholders so a board could be drawn. They are not decisions.

| ID | Used here | Why |
|---|---|---|
| RA-1 IMU | ICM-20948 with 1.8 V LDO and I2C translator | The netlist part. Lifecycle status not checked. |
| RA-2 Outline | A: HAT+ outline, EGT bank off-board on J11 | Doc 06 recommendation |
| RA-3 TC connectors | 3.5 mm 2-pole terminal blocks, wires leaving over the top edge | Keeps leads off the board; other edges are taken by the extension and J2 |
| RA-4 Power | Pi 3V3, as in the netlist | Fewest added parts. Doc 06 prefers a local LDO. |
| RA-5 BME680 | On-board peninsula with milled slots and no copper pour | Doc 06 |
| RA-6 HAT+ ID pins | RB-EMS mapping unchanged (I2C0 on GPIO0/1) | Matches the netlist; keeps the HAT+ deviation |
| RA-7 Off-HAT signals | No connectors | Not in the netlist |

## Added parts (not in netlist.csv)

The DIY modules carry these on board; a chip-down board has to supply them.

| Refdes | Purpose |
|---|---|
| U15, R14-R16, C21 | PCA9306 between 3V3 I2C1 and the IMU's 1.8 V I/O, EN network, 1.8 V pull-ups |
| U16, C19, C20 | AP2112K-1.8 LDO for the IMU |
| C16-C18 | IMU VDD, VDDIO and REGOUT capacitors |
| J3-J6 | CHT1-CHT4 terminal blocks |
| C4-C15 | MAX31856 AVDD, DVDD and T+/T- capacitors |
| C22-C25, R17-R19 | BME680, ADS1115 and U14 decoupling, 5 V pull-ups, U14 EN network |
| R20-R23, C26-C29 | ADC input RC filters |

U13, R13 and TP1 are DNP on the DIY build but fitted here, because HAT+ needs the ID EEPROM.

## Not done

A real Rev A needs at least these:

- **A schematic and ERC.** There is no schematic: the board comes straight from the CSV and the tables in `generate.py`.
- **FFC access.** The HAT+ examples have a PCIe FFC cut-out in the left edge (y 20-37) and a display FFC slot.
  RB-01 uses both PCIe and DSI. This board has neither, and the BME680 peninsula sits in that left-edge band.
- **Second ADS1115 at 0x49.** rb-ems-go now reads `oilpressure` there, so A3 is out of date. See below.
- **Doc 06 circuitry left out:** 33 Ohm series resistors on SCLK and MOSI, clamps and the battery divider on the
  ADC inputs, ferrite-split supplies.
- **Thermocouple layout.** No isothermal copper islands, and T+/T- are not routed as tight pairs.
- **Layout review.** `generate.py` holds a simple maze router: no length or impedance control, and nobody has
  reviewed the routing, the return paths or the assembly.
- **Footprint checks.** `MS4525DO_DS_DIP-8` is drawn from the datasheet outline; confirm pads and drills against
  TE's current drawing. U1 uses a generic 3 x 3 mm QFN-24 with the exposed pad removed, because the ICM-20948 die
  pad must not be soldered; confirm it against the TDK land pattern.

## Known differences from the docs

- **Header position.** [docs/03-mechanical.md](../../../docs/03-mechanical.md) puts the 40-pin header at x = 29 from
  the board corner. The Pi 5 drawing and the HAT+ examples measure that 29 from the hole, so the centre is at
  x = 32.5 and pin 1 at x = 8.37. This board uses the drawing.
- **ADC channels.** Since rb-ems-go `55f0627` (2026-10-10), `ems-adc.json` reads A2-A3 as a differential pair and
  `oilpressure` at address 0x49. J2 and U8 follow `netlist.csv`, which still has oil pressure on A3.

## Render notes

- The MS4525DO 3D model is a simple one made by `generate.py` from the datasheet outline.
- U8 shows KiCad's MSOP-10 model, because the library has no VSSOP-10 model. The outline is the same.
- Straight-down views use side lights only, because a light on the vertical axis mirrors off the mask and turns it
  pink. Their cast shadows are off, through a throwaway `KICAD_CONFIG_HOME`; your own KiCad settings aren't touched.

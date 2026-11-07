# CLAUDE.md - RB01HAT (Raspberry Pi 5 sensor HAT for the RB-04 EMS)

Repo-wide rules (reference design, commercial boundary, git) are in the root [CLAUDE.md](../../CLAUDE.md).

## What this project is

A sensor HAT for the **Raspberry Pi 5** in the RB avionics EMS. It carries a 9-axis IMU, an air-quality sensor,
8 thermocouple channels (4 CHT + 4 EGT), a differential-pressure (airspeed) sensor and a 4-channel ADC.

- **Pin mapping authority: rb-ems-go** (sibling repo at `../../../rb-ems-go`, Go daemons with JSON configs), plus its
  pinout image `RB-01-PIN.jpg` (v3.0) where the JSON is silent. Details and discrepancies:
  `docs/07-rb-ems-alignment.md`. rb-ems-go is safety-critical. **Never edit it from here**; list the changes it needs
  in doc 07 instead.
- **Rev 0 (now)**: DIY build on a red 65 x 56 mm "Proto HAT w/EEP" (AliExpress 1005010001574209) with breakout
  modules in sockets, wired with a pre-formed U-jumper kit (AliExpress 1005004505328512) or plain wire. The EGT bank
  sits on a 3D-printed extension plate over the Pi's USB/Ethernet block.
- **Rev A (next)**: custom PCB in KiCad, derived from the same netlist.

Status: design data and docs are ready. Nothing has been built or tested on hardware yet.

## Device priority (the user's allocation order) and pins (from rb-ems-go)

| P | Device | Bus / signals | Where |
|---|---|---|---|
| 1 | ICM-20948 (U1) | I2C1 0x69 (INT not wired) | HAT Z1 |
| 2 | BME680 (U2) | I2C0 0x77 ("I2C air quality") | HAT Z2 (edge overhang) |
| 3 | 4x MAX31856 CHT1-CHT4 (U3-U6) | SPI1, CS GPIO13/26/6/27 | HAT Z3 |
| 4 | MS4525DO (U7) | I2C1 0x28 (assumption: not in rb-ems-go) | HAT Z4 |
| 5 | ADS1115 (U8) + translator (U14) | I2C0 0x48, VDD 5 V behind U14 | HAT Z5 |
| 6 | 4x MAX31856 EGT1-EGT4 (U9-U12) | SPI0 via J11/J12 ribbon, CS GPIO23/8/24/7 | Extension plate |

All 28 GPIOs are assigned by the RB system. The ones the HAT doesn't use belong to off-HAT RB functions: GPS UART
14/15, FLARM 4/5, RPM 22, landing gear 25/12/16, the 5th MAX31856 on GPIO17, and GPIO18 (spidev1 CE0, do not
connect). When something has to give, cut from the bottom of the priority list.

## Repository map

```
CLAUDE.md                 this file
README.md                 overview and quick start
Makefile                  make check | make docs | make rbems | make pins
hardware/                 SOURCES OF TRUTH (CSV)
  pi5-header.csv          40-pin header: physical pin -> BCM GPIO
  gpio-reserved.csv       GPIOs the HAT must not use (rb-ems = off-HAT RB function; reserved = do not connect)
  parts.csv               every refdes: priority, bus, I2C address, supply, location, DNP
  netlist.csv             every connection; row order within a net = physical daisy-chain order
  bom-diy.csv             purchasing list (every fitted refdes must appear here)
  kicad/                  Rev A KiCad project (placeholder)
  kicad/rb01hat-concept/  generated visualisation, do not fabricate; change generate.py, not the KiCad files
docs/
  01-requirements.md      requirements (R6 = rb-ems-go mapping), priority interpretation, assumptions, questions
  02-architecture.md      buses, pull-ups, 5 V island, power budget, software architecture
  03-mechanical.md        Pi 5 dimensions, stack height options, zone plan, keep-outs
  04-diy-build.md         step-by-step DIY build, jumper-kit usage, build stages
  05-bringup.md           pre-power checks, Pi setup, bring-up script, troubleshooting
  06-custom-pcb.md        Rev A plan, HAT+ checklist (with the I2C0 deviation), open decisions RA-1 to RA-7
  07-rb-ems-alignment.md  mapping vs rb-ems-go, JSON-vs-image discrepancies, changes rb-ems-go needs
  08-rb01-system.md       RB-01 high-level system diagram (generated SVG) and interface table
  references.md           datasheets and links, plus the facts already checked
  generated/              GENERATED from hardware/*.csv - never edit by hand
mechanical/extension-plate.md   spec of the plastic extension (EGT bank carrier)
software/
  boot-config.txt         lines for /boot/firmware/config.txt (i2c0-pi5, spi0-0cs, spi1-1cs, i2c_arm)
  bringup/rb01hat_bringup.py    hardware verification; reads its pin map from hardware/*.csv
tools/netlist.py          validator, doc generator, rb-ems-go cross-check (stdlib only)
tools/rb01_diagram.py     generates docs/generated/rb01-system.svg from its component lists (stdlib only)
```

## Workflow (always)

1. Change hardware **only** in `hardware/*.csv`. Refdes, net names and pin assignments live there and nowhere else.
2. Run `make check`. It must report 0 errors. The single warning about the DNP EEPROM WP net is expected.
3. Run `make rbems RB_EMS_GO=../../../rb-ems-go` (the Makefile default doesn't resolve from this folder). The only
   error allowed is the known `oilpressure` one under Open items. Its warnings list what rb-ems-go still has to change
   (EGT kind/spiMode, busSpeed). Any pin change must agree with the rb-ems-go JSON; if it can't, ask the user first.
4. Run `make docs` to regenerate `docs/generated/` (gpio-map.md, wiring-list.md, rb01-system.svg).
5. Update the hand-written docs the change affects (02 allocation, 03 placement, 07 alignment) and this file's
   priority table if a pin or address changed.
6. After touching `software/bringup/`, run `python3 -m py_compile` and `make pins` (both work without hardware).

`make check` rejects: header pins used twice, GPIOs tied to power, reserved/rb-ems GPIOs used (GPIO0/1 only as
I2C0), I2C address clashes, shared or missing chip-selects, parts on the wrong bus net, supply pins on the wrong
rail, 3V3 parts on the 5V rail, 5 V part I/O wired straight to a GPIO, parts missing from the netlist or the BOM,
and J11/J12 pin mismatches.

## Design invariants (do not break without an explicit user decision)

- **Pins come from rb-ems-go.** CHT on SPI1 (`/dev/spidev1.0`), EGT on SPI0 (`/dev/spidev0.0`), all chip-selects
  manual GPIOs, ADS1115 on I2C0 at 0x48.
- **Boot overlays**: `dtoverlay=spi0-0cs` (GPIO7/8 are EGT4/EGT2 chip-selects; **never** `dtparam=spi=on`),
  `dtoverlay=spi1-1cs` (GPIO18 = kernel CE0, leave unconnected), `dtoverlay=i2c0-pi5` (not `i2c_vc`),
  `dtparam=i2c_arm=on`.
- **3V3 everywhere except the ADS1115**, which runs at 5 V (keeps rb-ems-go's 0-5 V `gain_mv 6144` scaling) behind
  the U14 level translator. 5 V comes from pin 4 and reaches only U14's high side and U8.
- **I2C0 on GPIO0/1 carries sensors.** This is a documented HAT+ deviation. The Pi has no pull-ups there, so R11/R12
  (3.9 kOhm) are fitted. Keep 0x49 free (the RB image's second ADS1115).
- **Every CS line has a 10 kOhm pull-up to 3V3.** GPIO power-on pulls are unspecified, and a low CS would make SDO
  outputs fight on MISO.
- **No interrupt or fault lines** (no free GPIO): IMU INT, MAX31856 FAULT/DRDY and ADS1115 ALERT are NC. Software
  polls the status registers.
- **The ICM-20948 needs 1.8 V VDDIO** (1.71-1.95 V). Use only breakouts with a 1.8 V regulator and level shifters.
- **I2C pull-ups**: the combined value stays at or above ~1.1 kOhm per bus side.
- **Stack height**: with the Active Cooler, at least 15 mm board-to-board (16 mm ideal). DIY default is S1, about
  20 mm, which also puts the HAT above the USB stack.
- **SPI**: mode 1 for every MAX31856. 1 MHz recommended on hand wiring (chip max 5 MHz; rb-ems-go `busSpeed` is in
  micro-hertz). MAX31856 notch at 50 Hz.

## Conventions

- Always give pins both ways: `GPIO13 (pin 33)`. BCM numbers are for software; physical pins are for wiring.
- Thermocouple names match the rb-ems-go `name` fields: CHT1-CHT4, EGT1-EGT4 (functions in parts.csv end with them;
  `make rbems` compares them).
- Active-low nets end in `_N` (e.g. `CHT1_CS_N`). Power nets: `3V3`, `5V`, `GND`. A translated bus gets a suffix
  (`I2C0_SDA_5V`).
- Refdes: J = connector, U = IC or module, R/C/D = passives, TP = test point. `J1` is always the Pi header.
- Module pin names in the netlist are generic (VIN, GND, SDA, SCL, SCK, SDI, SDO, CS, FLT, DRDY, INT, ALRT, ADDR,
  A0-A3; translator LV/HV/LSDA/LSCL/HSDA/HSCL). Map them to the silkscreen of the actual module.
- Mechanical coordinates: top view, GPIO header at the top, USB/Ethernet to the right, origin at the Pi's top-left
  corner, mm. Zones Z1-Z6 are defined in `docs/03-mechanical.md`. Build stages 0-6 equal the priority numbers.
- Jumper kit colours encode **length**, not signal. Never infer a net from a wire colour.
- The proto board's labelled GPIO column is **re-ordered** compared with the header. Always identify pins from the top
  of the board. The underside view is mirrored.
- The RB image labels SPI1 pin 35 "MOSI" and pin 38 "MISO". On the Pi, GPIO19 (pin 35) is SPI1 **MISO** and GPIO20
  (pin 38) is SPI1 **MOSI**. Wire by Pi function.

## Hardware facts already checked (see docs/references.md)

- MAX31856: 3.0-3.6 V, SPI CPHA=1, 5 MHz max, SDO high-Z while CS is high. Defaults: CR0=0x00, CR1=0x03 (type K),
  MASK=0xFF. The bring-up script uses CJTO (0x09) for its CS write/readback test. Change the notch only in
  normally-off mode.
- MS4525DO ordering code: interface I/J/K = 0x28/0x36/0x46; digits 0-9 = 0x48-0x51 (0 clashes with an ADS1115).
  Supply digit 3 = 3.3 V. Needs 100 nF within 2 cm. Avoid the -L/-M low-power options.
- ICM-20948: WHO_AM_I = 0xEA. The magnetometer is the AK09916 at 0x0C in bypass mode (WIA 0x48, 0x09).
- BME680 chip ID = 0x61. ADS1115 config reset value = 0x8583.
- HAT+: CAT24C32 EEPROM at 0x50, 3.9 kOhm ID pull-ups, 1 kOhm WP pull-up and a test pad.
- Pi 5 overlays: `i2c0-pi5` (GPIO0/1), `spi0-0cs` (keeps spidev0.0, frees GPIO7/8), `spi1-1cs` (CE0 GPIO18),
  `uart2-pi5` (GPIO4/5).
- rb-ems-go opens each spidev once, with the first sensor's spiMode. `busSpeed` is periph micro-hertz.

## Open items

- Confirm the JSON-vs-image discrepancies in doc 07 (EGT numbering, CHT1 GPIO5 vs 13, GPIO17 OAT vs oil temp,
  ADS channel 1, SPI1 labels).
- `make rbems` reports 1 error: rb-ems-go `ems-adc.json` reads `oilpressure` at I2C0 0x49, and the HAT has no ADS1115
  there. `netlist.csv` also still has oil pressure on A3, while rb-ems-go `55f0627` reads A2-A3 as a differential pair.
  Decide whether the HAT follows.
- rb-ems-go changes for the HAT: EGT `kind` MAX31856K and `spiMode` 1, `busSpeed` 1000000000000. The boot overlays
  go on the RB unit.
- Check the existing RB-01 wiring: a 5 V ADS1115 module wired straight to GPIO0/1 puts 5 V on Pi GPIOs.
- User decisions: ADS1115 at 5 V plus translator vs 3.3 V plus dividers; connectors for off-HAT RB signals (RA-7);
  HAT+ ID-pin deviation (RA-6); the ICM-20948 address the RB-01 driver expects.
- Measure the real USB/Ethernet heights and the chosen riser, then fix the stack option (S1 vs S2).
- Check the full stack (battery-backup HAT, PCIe USB HAT, RB01HAT + extension plate) against the STL models the
  user will import (`docs/08-rb01-system.md`).
- After the dry fit, write the as-built zone positions into `docs/03-mechanical.md` and the board map into
  `docs/diy-board-map.md`.
- CAD for the extension plate (`mechanical/`). KiCad Rev A decisions RA-1 to RA-7 (`docs/06-custom-pcb.md`).

## Don'ts

- Don't edit rb-ems-go or its configs from this project.
- Don't hand-edit `docs/generated/*`.
- Don't put anything on a GPIO listed in `gpio-reserved.csv`. Don't add GPIO-hungry features (interrupts, extra
  chip-selects) without first agreeing a pin change with the RB system.
- Don't add a module without qualifying it (checklist in `docs/04-diy-build.md` step 2) and recording its I2C address
  and supply in `parts.csv`.
- Don't state any datasheet value in the docs as fact until it has been checked. Add checked facts to the table in
  `docs/references.md`.

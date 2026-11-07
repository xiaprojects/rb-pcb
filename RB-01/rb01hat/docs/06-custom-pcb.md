# 06 - Custom PCB plan (Rev A)

Rev A turns the proven DIY netlist into a HAT+-compliant PCB. [hardware/netlist.csv](../hardware/netlist.csv) is the
starting point for the schematic. Only change it to reflect decisions made here, and keep `make check` passing.

## Tooling

- KiCad 9.x. Project in `hardware/kicad/rb01hat/` (see [hardware/kicad/README.md](../hardware/kicad/README.md)).
- Draw the outline and holes from the HAT+ mechanical drawing and the Pi 5 drawing (see [references.md](references.md)).
- Fab: 4-layer, 1.6 mm (L1 signals, L2 solid GND, L3 3V3 + GND, L4 signals). 2-layer is possible, but 4 layers help
  the thermocouple front-ends and the IMU.
- Assembly: have the fab place the fine-pitch parts (QFN/LGA). Hand-solder the through-hole connectors.

## HAT+ compliance checklist

- [ ] ID EEPROM: CAT24C32 (recommended by the spec) on ID_SD/ID_SC, with 3.9 kOhm pull-ups to 3V3.
- [ ] EEPROM WP to a 1 kOhm pull-up and a test pad (ground the pad to program).
- [ ] EEPROM at 0x50 ("Standard" class).
- [ ] **Known deviation (RB-EMS mapping)**: GPIO0/1 also carry I2C0 sensors (BME680, and the ADS1115 through its
      translator), while the spec allows only the EEPROM and its pull-ups. The board works, but it isn't strictly
      HAT+. To comply, move U2/U8 to I2C1 (addresses 0x77/0x48 are free there) and change rb-ems-go `ems-adc.json`
      `dev` to 1. Decision RA-6.
- [ ] STANDBY-compatible: 5 V on and 3V3 off must never back-power a GPIO. The ADS1115 (5 V) sits behind a
      translator that isolates with its low side unpowered. If a local 3.3 V LDO is used, **enable it from the Pi's 3V3**.
- [ ] External pulls wherever the power-on state matters (all eight CS lines).
- [ ] At least one hole aligned with the Pi. Ship the stacking header, spacers and screws for 16 mm or more (Active Cooler).
- [ ] Doesn't foul the PoE header. Doesn't block the camera/display/PCIe FFCs.
- [ ] EEPROM contents: vendor, product "RB01HAT", product ID and version, overlay name `rb01hat`. Build and flash
      with the tools in the spec (`eepmake`, `eepflash.sh -t=24c32`).

## Board outline options

| Option | Description | Stack |
|---|---|---|
| **A (recommended)** | HAT+ outline, 65 x 56.5 mm, carrying P1-P5 plus the CHT bank. The EGT bank goes on a small daughterboard on the extension plate, using the same J11/J12 ribbon as the DIY build. | 16 mm (S2) or 20 mm (S1) |
| B | One extended PCB (~88 x 56.5 mm) that also covers USB/Ethernet, with all 8 TC channels. | Must clear the USB stack (~16 mm, measure): needs 18-20 mm board-to-board (S1) plus a plastic foot or standoff over the Ethernet jack. |

## Subsystem notes

### Power

- Option 1: everything from the Pi's 3V3, as on the DIY build. Simplest.
- **Option 2 (preferred)**: local low-noise LDO from 5 V to 3.3 V (e.g. TLV75533 or AP2112K-3.3, 300-600 mA class),
  **EN driven by the Pi's 3V3** so it stays STANDBY-compliant. Split the thermocouple/ADC and IMU supplies with ferrite
  beads. Each group gets 10 uF + 100 nF.

### IMU (P1): ICM-20948

- QFN-24, 3 x 3 mm. VDD 1.71-3.6 V, **VDDIO 1.71-1.95 V**, so it needs a 1.8 V LDO, an I2C translator (e.g. PCA9306 or
  TCA9406), and an INT translator (e.g. SN74LV1T34 on 3.3 V).
- Check the part's lifecycle status before committing. If it is NRND/EOL, choose a 3.3 V-I/O IMU (e.g. the ICM-42688-P
  family) plus a separate magnetometer. That also removes the translators.
- Placement: near a mounting hole, away from switching regulators, inductors, current loops and the fan. No traces or
  vias under the package (follow the TDK layout guide).
- SPI1 now carries the CHT bank, and every other GPIO belongs to the RB system, so the IMU stays on I2C1.

### BME680 (P2)

- LGA-8, 3 x 3 mm: needs assembly.
- Thermal isolation: put it on a peninsula at the board edge with milled slots around it and no copper pour nearby,
  away from LDOs and Pi heat. Match it with an enclosure vent.
- Alternative: a 4-pin JST-SH (Qwiic/STEMMA QT) connector for a remote sensor board.

### Thermocouples (P3 + P6): 8x MAX31856

- TSSOP-14. 0.1 uF on AVDD and on DVDD.
- **100 nF differential capacitor across T+/T-** at every channel (the datasheet "strongly recommends" it). Add
  optional 10 nF from T+ and T- to GND for RF-noisy environments.
- Isothermal layout: each MAX31856 sits right next to its connector on a shared copper island, away from heat sources.
  The cold junction is the chip's internal sensor.
- Connectors: 2-pole 3.5 mm terminal blocks (~7 mm each; 8 fit along 56 mm), or miniature TC sockets (much wider;
  they may force outline B or a daughterboard).
- Series resistors on T+/T- only if fault voltages are expected. They add offset (datasheet "Effect of Series Resistance").
- Route T+/T- as a tight pair, away from SPI. Put 33 Ohm source-series resistors on SCLK and MOSI.
- Keep the 10 kOhm pull-ups on each CS. FAULT and DRDY are not routed (no free GPIO); software reads the status register.
- CHT bank on SPI1 (CS GPIO13/26/6/27), EGT bank on SPI0 (CS GPIO23/8/24/7), as in rb-ems-go.

### Differential pressure (P4): MS4525DO

- TE through-hole DIP with dual side ports (DS). 100 nF within 2 cm (datasheet). Use a 3.3 V part (`-DS3...`), with
  the ports at the board edge, and keep the tube routing clear.

### ADC (P5): ADS1115

- VSSOP-10. **VDD 5 V** (keeps rb-ems-go's 0-5 V scaling), ADDR to GND (0x48). I2C through a PCA9306 to 3.3 V I2C0.
  ALRT is not routed.
- Inputs coming from off-board: 1 kOhm series + 100 nF to GND (RC filter and current limit), a clamp to 0 V / 5 V
  (e.g. BAT54S), and a divider for the 12 V battery input. Differential pairs A0-A1 and A2-A3 are possible.
- Room for the RB image's second ADS1115 (0x49: fuel L/R, trim, flap) if wanted.

## Software / device tree

- Production software is rb-ems-go (user space, periph.io), with manual GPIO chip-selects. The board needs only the
  bus overlays in [software/boot-config.txt](../software/boot-config.txt): `i2c0-pi5`, `spi0-0cs`, `spi1-1cs`.
- An `rb01hat` overlay (named in the EEPROM so it loads automatically) can bundle those lines.
- Kernel IIO drivers (`maxim,max31856` with `cs-gpios`, `bosch,bme680`, `ti,ads1115`) are only worth it if rb-ems-go
  moves to IIO. They would claim the CS GPIOs and conflict with user-space chip-selects, so it's one or the other.

## Open decisions for Rev A

| ID | Decision | Options |
|---|---|---|
| RA-1 | IMU part | Keep ICM-20948 (with translators), or a newer 3.3 V IMU plus magnetometer |
| RA-2 | Outline | A (HAT+ board plus TC daughterboard) or B (extended board) |
| RA-3 | TC connectors | Terminal blocks or miniature TC sockets |
| RA-4 | Power | Pi 3V3 or a local LDO (EN from Pi 3V3) |
| RA-5 | BME680 | On-board peninsula or remote pigtail |
| RA-6 | HAT+ ID pins | Accept the I2C0 deviation (RB-EMS mapping as is) or move U2/U8 to I2C1 and update rb-ems-go |
| RA-7 | Off-HAT RB signals | Add connectors for GPS UART, FLARM, RPM, landing gear and the GPIO17 MAX31856, or leave them to the harness |

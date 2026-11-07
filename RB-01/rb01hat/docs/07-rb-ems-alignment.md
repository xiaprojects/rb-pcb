# 07 - Alignment with the RB-EMS system (rb-ems-go)

The HAT's pin mapping follows the RB-04 EMS software in `rb-ems-go` (`/home/stefano/rb-ems-go`). Its JSON configs
are the authority. The repository's pinout image `RB-01-PIN.jpg` ("RPI Board GPIO Scheme version 3.0, May 2026")
fills in what the JSON doesn't cover. Run `make rbems` after any pin change.

## Sources

| File (rb-ems-go) | What it defines |
|---|---|
| `ems-chtegt.json` | SPI thermocouples: `/dev/spidev1.0` MAX31856K (outsidetemperature, cht1-cht4), `/dev/spidev0.0` MAX31855 (egt1-egt4), manual CS GPIOs, `busSpeed` |
| `adc/ems-adc.json` | ADS1115 on I2C bus 0, address 0x48, channels 0-3 |
| `rpm/ems-rpm.json` | RPM pulse input on GPIO22 |
| `gpio/ems-gpio.json` | Landing gear switches on GPIO25 (nose), GPIO12 (left), GPIO16 (right) |
| `RB-01-PIN.jpg` | Full header scheme: I2C1 = IMU/BARO/MAG, I2C0 = ADS1115 + I2C air quality, UART GPS, FLARM out, second ADS1115 (0x49) |

## Header allocation (all 28 GPIOs are taken)

| GPIO (pin) | RB-EMS function | On the HAT |
|---|---|---|
| 0, 1 (27, 28) | I2C0: ADS1115, air quality | **Yes**: U8 ADS1115 (via U14), U2 BME680, R11/R12 pull-ups |
| 2, 3 (3, 5) | I2C1: IMU, BARO, MAG | **Yes**: U1 ICM-20948, U7 MS4525DO |
| 4 (7) | FLARM OUT (UART2 TX) to the traffic annunciators | no, off-HAT |
| 5 (29) | UART group with FLARM (UART2 RX) | no, off-HAT |
| 6 (31) | cht3 CS | **Yes**: U5 |
| 7 (26) | egt4 CS | **Yes**: U12 (extension) |
| 8 (24) | egt2 CS | **Yes**: U10 (extension) |
| 9, 10, 11 (21, 19, 23) | SPI0 MISO/MOSI/SCLK | **Yes**: EGT bank via J11/J12 |
| 12 (32) | landing gear left | no, off-HAT |
| 13 (33) | cht1 CS | **Yes**: U3 |
| 14, 15 (8, 10) | UART GPS | no, off-HAT |
| 16 (36) | landing gear right | no, off-HAT |
| 17 (11) | 5th MAX31856 CS (outsidetemperature) | no: reserved, not in the HAT list |
| 18 (12) | SPI1 CE0: do not connect | no |
| 19, 20, 21 (35, 38, 40) | SPI1 MISO/MOSI/SCLK | **Yes**: CHT bank |
| 22 (15) | RPM | no, off-HAT |
| 23 (16) | egt1 CS | **Yes**: U9 (extension) |
| 24 (18) | egt3 CS | **Yes**: U11 (extension) |
| 25 (22) | landing gear nose | no, off-HAT |
| 26 (37) | cht2 CS | **Yes**: U4 |
| 27 (13) | cht4 CS | **Yes**: U6 |

Consequences for the HAT:

- **No GPIO is left** for IMU INT, MAX31856 FAULT/DRDY or ADS1115 ALERT. They stay unconnected, and software polls
  (rb-ems-go already polls). The FAULT diode-OR network of the first draft has been removed.
- **GPIO7/8 are chip-selects**, so SPI0 must not claim them: use `dtoverlay=spi0-0cs`, **not** `dtparam=spi=on`.
- **GPIO18** is claimed by `dtoverlay=spi1-1cs` as the kernel CE0 for `/dev/spidev1.0`. Leave it unconnected (the
  image says so too).
- **I2C0 on the ID pins** (GPIO0/1) carries sensors. This is a deliberate **HAT+ deviation** (see doc 06). The Pi has
  no pull-ups there, so R11/R12 (3.9 kOhm) are fitted.

## Device mapping

| HAT ref | Requirement (priority) | rb-ems-go entry | Bus / CS |
|---|---|---|---|
| U1 | ICM-20948 (P1) | (not in rb-ems-go; RB-01 IMU in the image) | I2C1 0x69 |
| U2 | BME680 (P2) | image: "I2C AIR QUALITY" | I2C0 0x77 |
| U3-U6 | 4x MAX31856 (P3) | cht1, cht2, cht3, cht4 | SPI1, CS GPIO13, 26, 6, 27 |
| U7 | MS4525DO (P4) | (not in rb-ems-go or the image) | I2C1 0x28 (assumption: air-data bus) |
| U8 | ADS1115 (P5) | oilprobe/oiltemperature (ch0), rail50 (ch1), BatteryVoltage (ch2), Oilpressure (ch3) | I2C0 0x48 |
| U9-U12 | 4x MAX31856 (P6) | egt1, egt2, egt3, egt4 | SPI0, CS GPIO23, 8, 24, 7 |

This also answers assumption A1: the two "4xMAX31856" groups are the **4 CHT** probes (already MAX31856 in
rb-ems-go) and the **4 EGT** probes (MAX31855 today, MAX31856 on the HAT).

## Changes needed in rb-ems-go (not made here; that repo is safety-critical)

1. **EGT entries**: `kind` "MAX31855" to "MAX31856K" and `spiMode` 0 to 1, for **all four** egt sensors together.
   rb-ems-go opens each `/dev/spidevX.Y` once, using the first sensor's mode, so the modes on one device must match.
2. **`busSpeed`**: 5000000000000 is 5 MHz (periph `physic.Frequency` counts micro-hertz; the code comment says Hz).
   That is the MAX31856 maximum. For the hand-wired HAT plus the EGT ribbon, use **1000000000000 (1 MHz)**.
3. **Boot config** on the RB unit: [software/boot-config.txt](../software/boot-config.txt) (`i2c0-pi5`, `spi0-0cs`,
   `spi1-1cs`).

## ADS1115 supply: 5 V behind a level translator

`ems-adc.json` reads the 5 V rail ("rail50") and other channels at `gain_mv` 6144 with `r0` = 1. The image also shows
the second ADS1115 strapped "ADDR = 5V". Both mean the ADS1115 runs at **5 V** and reads 0-5 V signals directly.
Inputs must stay at or below VDD + 0.3 V, which 3.3 V could not deliver.

To keep the existing calibration untouched, the HAT powers U8 from 5 V and puts a level translator (U14: BSS138
module or PCA9306) between it and the 3.3 V I2C0 bus. The translator isolates when the Pi's 3V3 is off (STANDBY).
The ADS1115 module's own pull-ups are fine, because they now sit on the 5 V side.

**Check the existing RB-01 wiring:** if an ADS1115 module runs at 5 V and connects straight to GPIO0/1, its on-board
pull-ups (10 kOhm to VDD on Adafruit-style boards) hold those GPIOs at 5 V. Pi 5 GPIOs are 3.3 V only.

Alternative, if you'd rather keep everything at 3.3 V: power U8 from 3V3, drop U14, and divide every input down to
3.3 V. That changes `r0` in `ems-adc.json`, a scaling change rb-ems-go must not get without your confirmation.

## Discrepancies found between the JSON and the v3.0 image

The HAT follows the JSON in every case. Please confirm, then fix whichever source is wrong.

| # | Topic | `ems-chtegt.json` / `ems-adc.json` | `RB-01-PIN.jpg` v3.0 |
|---|---|---|---|
| 1 | EGT numbering | egt1 = GPIO23, egt2 = 8, egt3 = 24, egt4 = 7 | EGT1 = 7, EGT2 = 24, EGT3 = 8, EGT4 = 23 (reversed) |
| 2 | CHT1 chip-select | GPIO13 | connector label "CHT 1 [5]"; the header drawing shows G13 brown (MAX31856) and G5 green (UART) |
| 3 | GPIO17 sensor | `outsidetemperature` (r0 0.93) | "OIL T. [17]" |
| 4 | GPIO26 | cht2 | header label "G 26 FREE" (but brown, and the connector says CHT 2 [26]) |
| 5 | SPI1 data labels | - | pin 35 "G19 MOSI", pin 38 "G20 MISO": on the Pi, **GPIO19 = SPI1 MISO** and **GPIO20 = SPI1 MOSI**. The HAT wires by Pi function. |
| 6 | SPI0 labels | - | "G 19 / G 21 / G 23" are physical pin numbers (GPIO10/9/11) |
| 7 | ADS1115 channel 1 | `rail50` | "A1: Fuel Pressure" |
| 8 | Second ADS1115 | not configured | 0x49 (fuel L/R, trim, flap). Not on the HAT; address 0x49 on I2C0 kept free |

## Off-HAT signals

GPS UART (GPIO14/15), FLARM (GPIO4/5), RPM (GPIO22), landing gear (GPIO25/12/16) and the 5th MAX31856 (GPIO17) are
reserved in [hardware/gpio-reserved.csv](../hardware/gpio-reserved.csv). `make check` stops the HAT from using
them, and `make rbems` confirms rb-ems-go still sees them free.

Once the HAT sits on the header, those signals have to reach the harness through it. Open question: should the HAT
carry connectors for GPS, FLARM, RPM, landing gear and OAT/oil-temp? The proto board's labelled GPIO column gives
access to every pin.

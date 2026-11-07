# 04 - DIY build guide (Rev 0, proto HAT)

The per-wire checklist is [generated/wiring-list.md](generated/wiring-list.md). Print it and tick it off.

## 0. Tools and materials

Temperature-controlled iron with a fine tip, 0.5-0.7 mm solder, flux pen, multimeter with continuity beeper, flush
cutters, calipers, a 3.5 mm drill bit (to cut strips by hand), Kapton tape, IPA, and a loupe. Parts:
[hardware/bom-diy.csv](../hardware/bom-diy.csv).

## 1. Map the proto board (before soldering anything)

The silkscreen shows strips and rails. Verify every connection with the beeper anyway:

- [ ] The **labelled GPIO column**: which hole connects to which J1 pin. The column is re-ordered (SDA, SCL, TXD, RXD,
  #4, #17...). Never assume it follows the header order.
- [ ] Which **rails** are tied to which header pins (3V3, 5V, GND). **Only zone Z5 (ADS1115 + translator high side)
  uses 5 V.** Run one dedicated 5 V wire from pin 4 to Z5, and tape over or cut the board's 5V rail everywhere else,
  so a stray jumper can't put 5 V on a 3.3 V part or a GPIO.
- [ ] Strip direction and length in the main area.
- [ ] The **EEPROM footprint**: which pads go to ID_SD, ID_SC and WP.
- [ ] Which end has pin 1 (square pad). It should be the corner-notch end.

Record the result (photo plus notes) in `docs/diy-board-map.md` and fix any zone assumptions.

## 2. Qualify one module of each type (before buying all eight TC modules)

For each module type, check it against its schematic and with a meter:

- [ ] **Supply**: it runs from 3.3 V (the ADS1115 from 5 V). If it has an LDO (e.g. a "662K"), the chip may see about
  3.1-3.2 V. That is fine for the MAX31856 (3.0-3.6 V) and the BME680.
- [ ] **Pull-ups**: where they go (VIN, 3V3 or LDO output) and their value. Count the I2C pull-ups for the budget in
  [02-architecture.md](02-architecture.md#i2c-pull-up-budget).
- [ ] **Address strap default** (BME680: 0x76 or 0x77; ICM-20948: AD0).
- [ ] **ICM-20948 only**: there must be a 1.8 V VDDIO regulator and level shifters (Adafruit 4554 and SparkFun 15335
  qualify). Reject modules that put VDDIO on 3.3 V: VDDIO max is 1.95 V.
- [ ] **MAX31856 only**: SDO must go high-impedance when CS is high (datasheet Table 5). Some modules buffer SDO.
  To test: power the module with CS high. Tie SDO to 3V3 through 10 kOhm and it should read ~3.3 V; tie it to GND
  through 10 kOhm and it should read ~0 V. If it doesn't, the module can't share MISO.
- [ ] **MS4525DO**: check the part marking against A5 in [01-requirements.md](01-requirements.md). If it's a bare
  sensor, C3 (100 nF) must sit within 2 cm of its supply pin.
- [ ] **ADS1115 + U14**: the ADS1115 runs at 5 V; its pull-ups stay (they end up on the 5 V side). On the translator,
  find LV, HV, GND and which channel pins pair up (LV1 with HV1...). Check that its pull-ups go to LV on the low side
  and to HV on the high side.
- [ ] **Power LED**: remove it or cut its jumper. It saves 1-5 mA and keeps heat away from sensors.
- [ ] **Dimensions and pin order**: note them for the dry fit.

## 3. Dry fit (placement)

1. Solder female header sockets onto the modules' intended footprints **only after** the dry fit. First just lay
   every module, with its sockets, on the board, compare against the zone plan in
   [03-mechanical.md](03-mechanical.md#hat-zone-plan-top-view), photograph it and adjust.
2. Rules:
   - Every module sits in sockets, so it can be replaced.
   - IMU flat and rigid, axes parallel to the board edges, next to H1.
   - BME680 sensor overhanging the left edge (or on a pigtail).
   - MS4525DO ports out of the left edge.
   - TC cards vertical on right-angle headers, terminals on top, 10.16 mm (4-hole) pitch.
   - C1/C2 at the 3V3 rail entry near J1 pins 1/17.
   - Module pin rows run **across** the strips, so each pin gets its own strip. Otherwise cut the strips.
3. Record final positions in [03-mechanical.md](03-mechanical.md) ("as-built").

## 4. Header J1 and the stack

- J1 (female 2x20) goes on the **underside** and is soldered from the top.
- **Mirror trap**: seen from the underside, pin order is mirrored. Always identify pins from the top, using the
  labelled column and the pin-1 square pad.
- Tack two diagonal corner pins first. Mount the HAT on the Pi with the S1 riser and standoffs (see
  [03-mechanical.md](03-mechanical.md#stack-height-pi-to-hat)), check alignment and height, then solder the rest.
- Trim the leads and apply Kapton on the underside.

## 5. Wiring with the U-jumper kit

The kit's lengths are 0.1" spans. Check one against the grid (bend to bend) before trusting the table.

| Holes spanned | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 20 | 30 | 40 | 50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Kit label (mm) | 2 | 5 | 7 | 10 | 12 | 15 | 17 | 20 | 22 | 25 | 50 | 75 | 100 | 125 |
| Kit colour | dk green | blue | brown | grey | orange | red | yellow | green | blue | brown | grey | orange | red | yellow |

The board is roughly 25 x 22 holes, so lengths up to 25 mm do most of the work. For odd spans, cut a long jumper,
strip it, and re-bend it on the 2.54 mm grid.

**Colour means length, not signal.** Two ways to deal with that:

- Kit jumpers everywhere, identified only by the wiring list. This is quickest.
- **Recommended for the buses**: cut-to-length 22-24 AWG solid wire in a colour code. Where a kit jumper happens to be
  the right colour, use it.

| Signal | Colour |
|---|---|
| 3V3 | red |
| GND | black |
| I2C SCL | yellow |
| I2C SDA | blue |
| SPI SCLK | orange |
| SPI MOSI | green |
| SPI MISO | purple |
| CHTn_CS_N, EGTn_CS_N | white |
| 5V (Z5 only) | brown, plus a red tape mark |

Rules:

- Wires lie flat on the top side with Manhattan (right-angle) routing. Never route over a module socket or under a
  vertical card.
- **Daisy-chain** every bus in the order of the wiring list: no stars and no stubs. Run SDA and SCL side by side. Keep
  SPI SCLK away from the thermocouple terminals and the ADC inputs.
- Solder both legs, check for bridges to the next strip, and inspect with the loupe.
- Don't hold the iron on insulated sections of the jumpers; the PVC softens.
- Anything that leaves the board (pigtails, the ribbon, remote sensors) uses **stranded** wire. Solid wire breaks
  under vibration.
- Thermocouples: from sensor to module terminal, use only thermocouple or extension wire **of the same type**. A
  copper splice creates an extra junction and an error.

## 6. Build and test by stage (priority order)

After every stage: power off, inspect, beep the new nets against the wiring list, power on, and run the stage test
(details in [05-bringup.md](05-bringup.md)). Never plug modules or the ribbon in while powered.

| Stage | Build | Test command (`software/bringup/rb01hat_bringup.py ...`) |
|---|---|---|
| 0 | J1, 3V3 and GND rails, C1, C2, R11/R12 (I2C0 pull-ups). No modules, no 5 V yet. | Pre-power checklist, then 3.3 V on the rail; `i2cdetect -y 1` and `i2cdetect -y 0` are empty. |
| 1 | U1 socket, I2C1 chain | `all --fitted U1` |
| 2 | U2 socket, I2C0 chain | `all --fitted U1,U2` |
| 3 | SPI1 chain, R1-R4, U3-U6 (CHT1-CHT4) | `all --fitted U1,U2,U3,U4,U5,U6` |
| 4 | U7, C3 | `all --fitted U1,U2,U3,U4,U5,U6,U7` |
| 5 | 5 V wire to Z5, U14, U8, J2 | Before U8: 5 V only on U14 HV and the U8 socket VDD. Then `all --fitted U1,U2,U3,U4,U5,U6,U7,U8` |
| 6 | J11, R5-R8; extension plate with J12, U9-U12 (EGT1-EGT4) | `all` |

## 7. Finishing

- [ ] Label CHT1-CHT4 and EGT1-EGT4 on the board and plate, matching the rb-ems-go names. Identify each channel physically:
  warm one thermocouple at a time and watch which channel moves (swapped CS wires can't be detected electrically).
- [ ] Record the IMU axis orientation relative to the Pi.
- [ ] Magnetometer sanity check: read the magnetometer with the fan idle and at full speed. A large difference means
  the IMU is too close to a magnetic source: move it or calibrate with the fan running.
- [ ] Photograph the as-built board (top and bottom) into `docs/`.

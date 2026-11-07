# 05 - Bring-up and test

## Before the first power-on (every stage)

- [ ] Visual inspection: solder bridges, cold joints, and stray jumper legs on the underside.
- [ ] **3V3 to GND** at the HAT: no short. Expect open with no modules, and several kOhm or more with modules.
- [ ] **5V (J1.4)** reaches only U14 HV and U8 VDD. No continuity from 5V to the 3V3 rail or to any J1 GPIO pin.
- [ ] **5V to GND**: no short.
- [ ] Each CHTn_CS_N / EGTn_CS_N to 3V3: about 10 kOhm.
- [ ] J1.27 / J1.28 (I2C0) to 3V3: about 3.9 kOhm or less (R11/R12 plus module pull-ups).
- [ ] **Off-HAT pins have no connection on the HAT**: J1.7, 8, 10, 11, 12, 15, 22, 29, 32, 36 (GPIO4, 14, 15, 17,
      18, 22, 25, 5, 12, 16). They belong to the RB system (doc 07).
- [ ] Orientation: HAT pin 1 sits over Pi pin 1, both at the H1 corner.

## Raspberry Pi setup (once)

1. Raspberry Pi OS (Bookworm or newer, 64-bit), up to date.
2. Append [software/boot-config.txt](../software/boot-config.txt) to `/boot/firmware/config.txt`, then reboot.
   It enables I2C1, I2C0 (`i2c0-pi5`), SPI0 without kernel chip-selects (`spi0-0cs`) and SPI1 with one (`spi1-1cs`).
   Remove any `dtparam=spi=on` line: it grabs GPIO7/8, which are EGT chip-selects.
3. Install packages:
   `sudo apt install python3-smbus2 python3-spidev python3-gpiozero python3-lgpio i2c-tools`
4. The default user is already in the `i2c`, `spi` and `gpio` groups.
5. Copy this repository to the Pi. The script reads `hardware/*.csv`.

## First power-on

- Use the official 27 W supply. Measure 3.25-3.35 V on the HAT's 3V3 rail.
- `ls /dev/i2c-0 /dev/i2c-1 /dev/spidev0.0 /dev/spidev1.0` must list all four devices.
- `pinctrl get 7-8` must **not** show the SPI function on GPIO7/8.
- `i2cdetect -y 1` should show **28** and **69**. **0c** also appears once the script has put the IMU into bypass mode.
- `i2cdetect -y 0` should show **48** and **77** (0x76 with some BME680 modules), plus **50** if the EEPROM is fitted.

## The bring-up script

```bash
python3 software/bringup/rb01hat_bringup.py pins                  # resolved pin map, works on any PC
python3 software/bringup/rb01hat_bringup.py all --fitted U1,U2    # stage 2
python3 software/bringup/rb01hat_bringup.py all                   # everything fitted
make rbems                                                        # HAT vs rb-ems-go JSON (any PC)
```

The exit code is non-zero if any check fails. What each check proves:

| Check | Proves |
|---|---|
| `pullups` | With the Pi's internal pull-**down** on, every CHT/EGT chip-select still reads high, so the external pull-up is present and nothing holds the line low. |
| ICM-20948 | WHO_AM_I = 0xEA (I2C wiring and level shifter work). AK09916 answers at 0x0C in bypass mode. Acceleration magnitude is about 1 g at rest. (INT is not wired.) |
| BME680 | Chip ID 0x61 at the configured address. Warns if the part answers at the other address. |
| MS4525DO | Status bits are not "fault"; pressure is about 8192 counts (zero differential) with both ports open; temperature is plausible. |
| ADS1115 | Through U14 at 5 V: the config register reads back and four single-shot conversions complete at +/-6.144 V (the ems-adc.json `gain_mv`). (ALERT/RDY is not wired.) |
| MAX31856 | Per bus (CHT on SPI1, EGT on SPI0): a unique value written to CJTO on each CS reads back correctly. This proves the CS lines are distinct, MOSI/MISO/SCLK work, and no SDO fights the bus. Also: a cold-junction temperature, and the OPEN flag when no thermocouple is connected. If a CS GPIO is held by the kernel, the script names the overlay to fix. |

Limitation: **swapped** CS wires are electrically invisible (every chip still answers). Identify channels physically:
warm one thermocouple at a time and watch which channel moves.

## Thermocouple configuration used

CR0 = 0x01 then 0x51 (50 Hz notch, one-shot, open-circuit detection), CR1 = thermocouple type (K = 0x03, 1 sample),
MASK = 0xFF (FAULT output masked) during normal reads. Change the notch only while the chip is in normally-off mode
(datasheet). One conversion at 50 Hz takes 169-185 ms.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/dev/i2c-0`, `/dev/i2c-1`, `/dev/spidev0.0` or `/dev/spidev1.0` missing | config.txt not applied (on Bookworm the file is `/boot/firmware/config.txt`), or `i2c0-pi5` combined with `dtparam=i2c_vc=on`. |
| "cannot drive CS GPIO7/8" | `dtparam=spi=on` is still set. Use `dtoverlay=spi0-0cs`. |
| `i2cdetect -y 0` empty but I2C1 fine | R11/R12 missing (the Pi has no pull-ups on GPIO0/1), U14 unpowered, or LV/HV swapped on U14. |
| `i2cdetect` shows every address, or hangs | SDA/SCL shorted or swapped; a module holding the bus low. |
| `i2cdetect` shows nothing | SDA/SCL not connected, 3V3 rail open, or the module is unpowered. |
| ICM-20948 NACK or wrong WHO_AM_I | Module without a proper 1.8 V/level-shift design; AD0 low gives 0x68 (update parts.csv). |
| BME680 at 0x76 | Generic module. Set `i2c_addr` in parts.csv and run `make docs`. |
| MS4525DO NACK | Interface code J/K (0x36/0x46); a 5 V (DS5) part running at 3.3 V. |
| MS4525DO status=2 (stale) on every read | A low-power (-L/-M) part: it needs a measurement-request command before each read. |
| TC reads 0xFF | CS not reaching the module, module unpowered, or MISO open. |
| TC reads 0x00 | MISO shorted to GND, or the module is unpowered. |
| TC returns another channel's value | Those two CS lines are shorted together. |
| TC values random | SPI mode is not 1 or 3; clock too fast for the wiring (try 500 kHz); a module SDO not tri-stating; missing GND. |
| Cold junction reads 40-60 C | Warm air from the Pi. The TC reading stays valid as long as the terminal and chip are at the same temperature. |
| TC noisy (about +/-1 C) | Grounded thermocouple; 60 Hz notch selected in a 50 Hz country; SPI wires running next to the TC leads; missing 100 nF across T+/T-. |
| TC reading goes down when heated | Polarity reversed. For type K the negative leg (alumel) is magnetic. |
| Pi resets when the HAT is touched or plugged in | Short on 3V3, or hot-plugging. |

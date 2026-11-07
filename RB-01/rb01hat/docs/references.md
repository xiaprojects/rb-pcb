# References

## Raspberry Pi

- HAT+ specification (EEPROM, STANDBY, mechanics, 16 mm spacer recommendation): <https://datasheets.raspberrypi.com/hat/hat-plus-specification.pdf>
- HAT design guide and tools (legacy): <https://github.com/raspberrypi/hats>
- Raspberry Pi 5 mechanical drawing: <https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf>
- Raspberry Pi 5 product brief: <https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-product-brief.pdf>
- RP1 peripherals (Pi 5 GPIO, SPI, I2C): <https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf>
- config.txt and GPIO documentation: <https://www.raspberrypi.com/documentation/computers/raspberry-pi.html>
- Device-tree overlays README: <https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README>
- `spi0-0cs` overlay source: <https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/spi0-0cs-overlay.dts>
- Active Cooler and HAT clearance discussion: <https://www.raspberrypi.com/news/heating-and-cooling-raspberry-pi-5/>

## RB-EMS system (pin-mapping authority)

- rb-ems-go (local): `/home/stefano/rb-ems-go`. Configs: `ems-chtegt.json`, `adc/ems-adc.json`, `rpm/ems-rpm.json`,
  `gpio/ems-gpio.json`. Pinout image: `RB-01-PIN.jpg` (GPIO scheme v3.0, May 2026). Alignment: [07-rb-ems-alignment.md](07-rb-ems-alignment.md).

## Sensors

- ICM-20948 datasheet (TDK): <https://product.tdk.com/system/files/dam/doc/product/sensor/mortion-inertial/imu/data_sheet/ds-000189-icm-20948-v1.5.pdf>
- SparkFun ICM-20948 hookup guide (VDDIO and level shifting): <https://learn.sparkfun.com/tutorials/sparkfun-9dof-imu-icm-20948-breakout-hookup-guide/all>
- BME680 (Bosch): <https://www.bosch-sensortec.com/products/environmental-sensors/gas-sensors/bme680/>
- MAX31856 product page (ADI): <https://www.analog.com/en/products/max31856.html>. Datasheet mirror used: <https://cdn-learn.adafruit.com/assets/assets/000/035/948/original/MAX31856.pdf>
- MS4525DO datasheet (TE, 04/2019 mirror): <https://www.farnell.com/datasheets/3668668.pdf>
- ADS1115 (TI): <https://www.ti.com/product/ADS1115>

## Breakout modules (examples)

- Adafruit ICM-20948 (4554): <https://www.adafruit.com/product/4554>
- SparkFun ICM-20948 (SEN-15335): <https://www.sparkfun.com/products/15335>
- Adafruit BME680 (3660): <https://www.adafruit.com/product/3660>
- Adafruit MAX31856 (3263): <https://www.adafruit.com/product/3263>
- Adafruit ADS1115 (1085): <https://www.adafruit.com/product/1085>

## Purchased DIY items

- Proto HAT: <https://it.aliexpress.com/item/1005010001574209.html>
- U-jumper wire kit: <https://it.aliexpress.com/item/1005004505328512.html>

## Facts checked against the datasheets (2026-09-30)

| Fact | Source |
|---|---|
| ICM-20948 VDDIO 1.71-1.95 V, WHO_AM_I 0xEA | TDK datasheet |
| MAX31856: 3.0-3.6 V; 1.2/2 mA; SPI CPHA=1 (mode 1 or 3), 5 MHz max; SDO high-Z while CS is high; register defaults CR0 00, CR1 03, MASK FF; 50 Hz conversion 169-185 ms; 100 nF across T+/T- | Maxim/ADI datasheet |
| MS4525DO ordering code (DS = dual side port, 3 = 3.3 V, A = 10-90 %, I = 0x28, J = 0x36, K = 0x46, 0-9 = 0x48-0x51); 100 nF within 2 cm | TE datasheet |
| HAT+: CAT24C32, 3.9 kOhm ID pull-ups, 1 kOhm WP pull-up, 15-16 mm spacers with the Active Cooler, STANDBY rules, GPIO power-on pulls unspecified | HAT+ spec |
| `i2c0-pi5` puts I2C0 on GPIO0/1 (Pi 5 only); don't combine with `i2c_vc`. `spi0-0cs` claims no CS pins and keeps spidev0.0. `spi1-1cs` claims CS0 = GPIO18 and creates /dev/spidev1.0. `uart2-pi5` uses GPIO4/5 | Raspberry Pi overlays README and `spi0-0cs-overlay.dts` (rpi-6.12.y), checked 2026-10-05 |
| rb-ems-go: one periph SPI connection per spidev, opened with the first sensor's mode; `busSpeed` is a periph `physic.Frequency` (micro-hertz), so 5000000000000 = 5 MHz; ADS1115 opened as I2C bus `dev`; GPIO lines on gpiochip0 by BCM number | rb-ems-go source (`main/egt.go`, `adc/adc.go`, `gpio/gpio.go`, `rpm/rpm.go`) and periph `conn/v3/physic/units.go`, checked 2026-10-05 |

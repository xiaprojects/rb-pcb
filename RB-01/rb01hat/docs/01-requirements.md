# 01 - Requirements

## Requirements as given

| ID | Requirement |
|---|---|
| R1 | Raspberry Pi 5 HAT. |
| R2 | DIY version on the red proto HAT ([AliExpress 1005010001574209](https://it.aliexpress.com/item/1005010001574209.html)); a custom PCB will follow. |
| R3 | Wiring with standard wire or the pre-formed U-jumper kit ([AliExpress 1005004505328512](https://it.aliexpress.com/item/1005004505328512.html)). |
| R4 | The HAT mounts on top of the Pi; a plastic extension over the Ethernet/USB side is allowed if needed. |
| R5 | Allocate by priority: 1 ICM20948, 2 BME680, 3 4xMAX31856, 4 MS4525DO, 5 ADS1115, 6 4xMAX31856. |
| R6 | The Raspberry Pi 5 pin mapping follows the rb-ems-go JSON configuration (`/home/stefano/rb-ems-go`). See [07-rb-ems-alignment.md](07-rb-ems-alignment.md). |

### What the two purchased items are

- **Proto HAT**: "DIY Prototyping Pi HAT for Raspberry Pi 5/4/3" (red). 65 x 56 mm HAT outline, 4 M2.5 holes on the
  58 x 49 mm Pi pattern, a corner notch at the pin-1 end, a labelled column that breaks out every GPIO, power rails,
  strip-connected prototyping area and an SOIC-8 ID EEPROM footprint with a WP pad ("Proto HAT w/EEP"). It comes
  with a 2x20 female header, 4 brass standoffs, screws and nuts.
- **Jumper kit**: YIDI 140/560/840-piece pre-formed U jumpers, 14 lengths labelled 2/5/7/10/12/15/17/20/22/25/50/75/100/125 mm.
  These are 0.1" spans (1-10, 20, 30, 40, 50 holes). **Colour encodes length, not signal.**

## How "allocate by priority" is applied

Priority decides four things, in this order:

1. **What gets in.** If something has to be dropped or deferred, cut from the bottom (P6 first).
2. **Board position.** P1 gets the best spot (rigid and magnetically quiet); the lowest priority goes onto the extension.
3. **Header GPIOs.** R6 fixes these: rb-ems-go assigns every pin. Priority only decides what gets dropped when no
   pin is left (IMU INT, thermocouple FAULT/DRDY and ADS1115 ALERT are not wired).
4. **Build and test order.** The DIY board is built and verified one stage at a time, in priority order (the "Stage"
   column in [generated/wiring-list.md](generated/wiring-list.md)).

| P | Device | Qty | Bus / signals (rb-ems-go) | Location | Why there |
|---|---|---|---|---|---|
| 1 | ICM-20948 9-axis IMU | 1 | I2C1 0x69 (INT not wired) | HAT zone Z1 (top-left) | Rigid corner by a standoff, away from the fan motor and the PMIC inductors |
| 2 | BME680 air quality | 1 | I2C0 0x77 | HAT zone Z2, sensor hanging over the left edge (or on a pigtail) | Must be away from the Pi's heat |
| 3 | MAX31856 CHT bank (CHT1-CHT4) | 4 | SPI1, CS on GPIO13/26/6/27 | HAT zone Z3 as vertical cards | Right under SPI1 pins 31-40 |
| 4 | MS4525DO differential pressure | 1 | I2C1 0x28 | HAT zone Z4, ports out of the left edge | Needs tube access at an edge |
| 5 | ADS1115 4-ch ADC (+ U14 translator) | 1 | I2C0 0x48, VDD 5 V | HAT zone Z5 + terminal J2 | Needs no special spot |
| 6 | MAX31856 EGT bank (EGT1-EGT4) | 4 | SPI0 via ribbon, CS on GPIO23/8/24/7 | Extension plate over USB/Ethernet | Lowest priority: goes off the HAT |

## Assumptions (confirm or correct)

| ID | Assumption | If wrong |
|---|---|---|
| A1 | The two "4xMAX31856" groups are the 4 CHT and the 4 EGT probes of rb-ems-go (inferred from the JSON: CHT is MAX31856 already, EGT is MAX31855 today). | If the EGTs stay on MAX31855: change U9-U12 in the CSVs; the MAX31855 is read-only and needs SPI mode 0. |
| A2 | Type K thermocouples with insulated (ungrounded) junctions. | Type is set per channel in software (MAX31856 CR1). Grounded junctions need a review (common-mode and ground loops). |
| A3 | The Raspberry Pi Active Cooler is fitted. | Without it the stack could be lower, but the Pi 5 will throttle under load. |
| A4 | 50 Hz mains (Italy). The MAX31856 notch filter is set to 50 Hz. | Change CR0 bit 0. |
| A5 | MS4525DO is a 3.3 V part (DS3) with interface code I (0x28), +/-1 psi differential (e.g. MS4525DO-DS3AI001DP). | Codes J/K give 0x36/0x46. A DS5 (5 V) part needs a 5 V supply plus an I2C level shifter. |
| A6 | Every sensor runs from the Pi's 3V3, **except the ADS1115**, which runs at 5 V behind a level translator (U14) so rb-ems-go's 0-5 V scaling stays unchanged. | Option: ADS1115 at 3.3 V with input dividers. That changes `r0` in ems-adc.json. |
| A7 | IMU on I2C1 is enough. SPI1 now belongs to the CHT bank, so there is no IMU-on-SPI upgrade path. | Revisit in Rev A if higher IMU rates are needed. |
| A8 | ADS1115 inputs: oil temperature probe, rail50 / fuel pressure, battery (external divider), oil pressure, all 0-5 V at the pin. | See discrepancy 7 in doc 07. |
| A9 | MS4525DO goes on I2C1 with the IMU (air data). It is in neither rb-ems-go nor the image. | Any bus works: 0x28 is free on both. |

## Non-functional requirements

| ID | Requirement |
|---|---|
| N1 | The custom PCB complies with HAT+ (ID EEPROM, ID pins, STANDBY, mechanics). See [06-custom-pcb.md](06-custom-pcb.md). |
| N2 | The DIY build can be serviced: every module sits in a socket. |
| N3 | Measurement quality: the BME680 is thermally decoupled, the IMU sits away from magnetic sources, and each MAX31856 is at the same temperature as its terminal. |
| N4 | Nothing blocks the Pi's FFC connectors (camera/display, PCIe), the power button, the fan connector or the USB/Ethernet plugs. |

## Open questions

1. Confirm A1 (CHT + EGT) and the JSON-vs-image discrepancies in [07-rb-ems-alignment.md](07-rb-ems-alignment.md).
2. Thermocouple type(s) and temperature range? Screw terminals or miniature TC plugs?
3. What will the ADS1115 measure (voltage range, source impedance)?
4. What is the exact MS4525DO part number (supply DS3/DS5, interface I/J/K, range, output type A/B)? A bare sensor or a drone airspeed module?
5. Enclosure and environment (lab, vehicle, drone)? This drives IMU mounting, connector locking and strain relief.
6. Required sample rates (IMU, thermocouples, ADC)?
7. Should the HAT carry connectors for the off-HAT RB signals (GPS UART, FLARM, RPM, landing gear, the 5th MAX31856 on GPIO17)?
8. Which I2C address does the RB-01 IMU driver expect for the ICM-20948 (0x68 or 0x69)?

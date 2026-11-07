# 03 - Mechanical

## Coordinate system

Top view. The Pi's GPIO header runs along the **top** edge, USB/Ethernet are on the **right**, and the origin is the
top-left corner of the Pi PCB. x points right, y points down, units are mm. The HAT uses the same coordinates, because
its holes sit directly above the Pi's.

## Raspberry Pi 5 reference

From the [Raspberry Pi 5 mechanical drawing](https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf)
(approximate, reference only):

| Feature | Position / size |
|---|---|
| PCB | 85 x 56 mm |
| Mounting holes | 4x dia. 2.7 mm (M2.5) at (3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5): a 58 x 49 mm pattern |
| 40-pin header | centred at x = 29, y = 3.5. Pin 1 at the left (H1) end. Even pins are the outer row. |
| USB / Ethernet | right edge, protruding ~3 mm (to x = 88). Heights are not on the drawing: RJ45 about 13.5 mm, USB stack about 16 mm. **Measure with calipers.** |
| USB-C, 2x micro-HDMI | bottom edge at x = 11.2, 25.8, 39.2 |
| 2x CAM/DISP FFC | bottom-right area under the HAT, x about 47-57 |
| PCIe FFC | left edge, under the HAT |
| Power button | left edge, y about 37.6 |
| PoE header (2x2) | near the bottom-right hole, about x 59-64, y 44-49: **keep the HAT underside clear there** |
| Fan connector + Active Cooler push-pin hole | near the top-right hole (61.5, 3.5) |

## Stack height (Pi to HAT)

The HAT+ spec asks for **at least 15 mm board-to-board, ideally 16 mm**, when the Active Cooler is fitted. The proto
kit's short header and standoffs give about 11-12.5 mm, which only works without the Active Cooler.

| Option | Build | Board-to-board | Verdict |
|---|---|---|---|
| **S1 (recommended for DIY)** | Pi header, then a 2x20 riser (8.5 mm female body, long male pins), then the HAT's own 8.5 mm female header. 20 mm standoffs. | ~19.5-20 mm (measure) | Clears the Active Cooler with airflow margin. The HAT underside sits **above the USB stack**, so a **flat** extension plate can pass over USB/Ethernet. |
| S2 (HAT+ nominal) | A ~13.5 mm-tall female header on the HAT, or a riser sized for 16 mm. 16 mm standoffs. | 16 mm | Meets the spec, but the HAT is at USB-stack height. The extension plate has to sit on top of the HAT, with only ~1.5 mm of margin. |
| S0 | Kit header and standoffs | ~11-12.5 mm | Only without the Active Cooler. Not recommended. |

With S1, check that the male pins engage the HAT socket by at least 5 mm, and that the standoffs don't leave the header
hanging or bottomed out. Shim with M2.5 washers if needed.

Height budget (S1): top of the HAT PCB is about 21.5 mm above the Pi PCB. Socketed modules add about 12 mm, and the
vertical TC cards about 25-30 mm. Plan for **about 50-55 mm above the Pi PCB** when designing an enclosure.

## HAT underside rules

- The underside carries only J1. Trim every through-hole lead to 1.5 mm or less.
- Put Kapton tape over the area above the Active Cooler and the PoE header.
- Nothing may touch the Active Cooler's fan intake (the fan hub). With S1 there is plenty of room.

## HAT zone plan (top view)

Approximate zone boundaries. Adjust them after the dry fit with the actual modules (see
[04-diy-build.md](04-diy-build.md) step 3), then record the as-built positions here.

```
       x=0              23                                         65
y=0    +--notch--------------------------------------------------------+
       | H1  [ J1 2x20 GPIO header: pin 1 ...................... pin 39 ] H2 |
       |     C1 C2 at the 3V3 entry | labelled GPIO column | rails        |
y~11   +------------------+--------------------------------------------+
       | Z1 ICM-20948  P1 | Z3 CHT bank  P3   U3  U4  U5  U6           |
       | flat, rigid,     | 4 vertical cards, 10.16 mm pitch           |
       | axes = board     | terminals on top; R1-R4 at the card feet   |
y~33   +------------------+-----------------------------+--------------+
       | Z2 BME680     P2 | Z5 ADS1115 + U14 (5 V)  P5  | Z6 J11 2x5   |
       | sensor overhangs |                             | R5-R8 (EGT)  |
y~45   | left edge  <---- | J2 terminal at bottom edge  | ribbon -> EXT|
       | Z4 MS4525DO P4 C3|                             |              |
       | ports out  <---- |                             |              |
y=56   +-H3---------------+-----------------------------+-----------H4-+
```

Why these positions:

- **Z1 IMU (P1)**: top-left, next to standoff H1 (the stiffest area). It sits above the Pi's wireless module can,
  which is not magnetic. It stays away from the PMIC and its inductors (Pi bottom-left, near USB-C), the Active Cooler
  fan motor, and the SoC hot spot. Mount it flat with its axes parallel to the board edges, and record which way the
  axes point.
- **Z2 BME680 (P2)**: the sensor hangs past the left edge of the Pi, into ambient air. It sits on I2C0 (pins 27/28,
  mid-header), so its SDA/SCL run left along the header. If readings still run warm, move it to a 10-20 cm pigtail
  (4-wire I2C, stranded wire or a JST-SH / Qwiic cable).
- **Z3 CHT bank (P3)**: cards stand vertically with their terminals on top, so the thermocouple leads leave upward and
  never cross the board. SPI1 (pins 35/38/40) and three of the CHT chip-selects (pins 31/33/37) are right above this
  zone. CHT4's CS comes from pin 13.
- **Z4 MS4525DO (P4)**: pneumatic ports point out of the left edge. Tubes must not kink or press on the sensor.
- **Z5 ADS1115 (P5) + U14 + J2**: the only 5 V area of the HAT (5 V from pin 4). Keep it compact, with U14 between
  I2C0 and the ADS1115. J2 sits at the bottom edge for field wiring.
- **Z6 J11 (P6)**: the EGT ribbon connector is at the right edge, facing the extension. SPI0 (pins 19/21/23) and the
  EGT chip-selects (pins 16/18/24/26) come from the middle of the header.

## Extension plate over USB/Ethernet

The extension carries the EGT bank (P6). Full specification: [mechanical/extension-plate.md](../mechanical/extension-plate.md).

Summary: a PETG or ASA plate (not PLA; it is close to the RP1 and Ethernet warmth), 3 mm thick with ribs. It is fixed
by two ears to the HAT's right-hand holes H2/H4 and spans x = 65-88. With S1 it sits about 5 mm above the USB stack. A
perfboard carrier on the plate holds four vertical MAX31856 cards (EGT1-EGT4) at 10.16 mm pitch, plus J12 and
strain-relief slots.

## Keep-outs checklist

- [ ] USB/Ethernet plugs insert fully, with the extension fitted.
- [ ] Camera/display FFC cables can be routed out (fit them before mounting the HAT).
- [ ] PCIe FFC is reachable at the left edge.
- [ ] The power button (left edge, y about 37.6) can be pressed.
- [ ] Fan cable and connector are not pinched.
- [ ] The PoE header doesn't touch the HAT underside.

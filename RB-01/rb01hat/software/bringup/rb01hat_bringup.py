#!/usr/bin/env python3
"""RB01HAT bring-up and wiring verification for Raspberry Pi 5.

The pin allocation is read from hardware/netlist.csv and parts.csv (through
tools/netlist.py), so the script always tests what the design files say.

Prerequisites (docs/05-bringup.md):
  /boot/firmware/config.txt : the lines in software/boot-config.txt (I2C0, I2C1, SPI0 without
                              kernel CS, SPI1 with one kernel CS), then reboot
  sudo apt install python3-smbus2 python3-spidev python3-gpiozero python3-lgpio i2c-tools

Usage:
  rb01hat_bringup.py pins                  resolved pin map (runs on any PC)
  rb01hat_bringup.py pullups               external pull-ups on every chip-select line
  rb01hat_bringup.py i2c                   I2C1: ICM-20948, MS4525DO; I2C0: BME680, ADS1115
  rb01hat_bringup.py tc                    every MAX31856 (CHT bank on SPI1, EGT bank on SPI0)
  rb01hat_bringup.py all
Options:
  --fitted U1,U2,U3   test only the refs mounted so far (incremental build by priority)
  --tc-type K         thermocouple type written to every MAX31856
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import netlist  # noqa: E402

# Linux device and the config.txt line that creates it, per bus name used in hardware/parts.csv.
# Chip-selects are plain GPIOs (as in rb-ems-go), so SPI0 must not claim GPIO7/8 (spi0-0cs) and
# SPI1 claims only GPIO18 (spi1-1cs), which stays unconnected.
BUS_DEVICES = {
    "I2C0": ("/dev/i2c-0", "dtoverlay=i2c0-pi5"),
    "I2C1": ("/dev/i2c-1", "dtparam=i2c_arm=on"),
    "SPI0": ("/dev/spidev0.0", "dtoverlay=spi0-0cs"),
    "SPI1": ("/dev/spidev1.0", "dtoverlay=spi1-1cs"),
}
SPI_HZ = 1_000_000           # MAX31856 max is 5 MHz; 1 MHz is safe for hand wiring + ribbon
SPI_MODE = 1                 # MAX31856 needs CPHA = 1 (mode 1 or 3)
TC_TYPES = {"B": 0, "E": 1, "J": 2, "K": 3, "N": 4, "R": 5, "S": 6, "T": 7}
SR_BITS = ["OPEN", "OVUV", "TCLOW", "TCHIGH", "CJLOW", "CJHIGH", "TC_RANGE", "CJ_RANGE"]


def s16(hi: int, lo: int) -> int:
    v = (hi << 8) | lo
    return v - 0x10000 if v & 0x8000 else v


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, ref: str, msg: str) -> None:
        self.rows.append((status, ref, msg))
        print(f"[{status:<4}] {ref:<4} {msg}", flush=True)

    def ok(self, ref: str, msg: str) -> None:
        self.add("OK", ref, msg)

    def fail(self, ref: str, msg: str) -> None:
        self.add("FAIL", ref, msg)

    def warn(self, ref: str, msg: str) -> None:
        self.add("WARN", ref, msg)

    def skip(self, ref: str, msg: str) -> None:
        self.add("SKIP", ref, msg)

    def summary(self) -> int:
        counts = {s: sum(1 for r in self.rows if r[0] == s) for s in ("OK", "WARN", "FAIL", "SKIP")}
        print("\n" + "  ".join(f"{k}={v}" for k, v in counts.items()))
        return 1 if counts["FAIL"] else 0


class Design:
    def __init__(self, fitted: str | None) -> None:
        self.p = netlist.load()
        errors, _ = netlist.check(self.p)
        if errors:
            raise SystemExit("hardware/*.csv has errors - run `make check`:\n  " + "\n  ".join(errors))
        self.fitted = {q.ref for q in self.p.parts.values() if not q.dnp}
        if fitted:
            chosen = {s.strip().upper() for s in fitted.split(",") if s.strip()}
            unknown = chosen - set(self.p.parts)
            if unknown:
                raise SystemExit(f"unknown refs in --fitted: {', '.join(sorted(unknown))}")
            self.fitted = chosen

    def parts_like(self, text: str) -> list[netlist.Part]:
        return sorted((q for q in self.p.parts.values() if text in q.part and q.ref in self.fitted),
                      key=lambda q: (q.priority, q.function))

    def gpio(self, ref: str, pin: str) -> int | None:
        return self.p.gpio_of(ref, pin)

    def net_gpio(self, net: str) -> int | None:
        hp = self.p.host_pin(net)
        return hp.bcm if hp else None


def tc_name(part: netlist.Part) -> str:
    return part.function.split()[-1]


# ----------------------------------------------------------------------------- pins

def print_pins(d: Design) -> None:
    print(f"{'Ref':<5}{'Function':<34}{'Pin':<6}{'Net':<12}{'GPIO':>5}{'J1':>5}")
    for part in sorted(d.p.parts.values(), key=lambda q: (q.priority, netlist.ref_key(q.ref))):
        if part.ref not in d.fitted or part.kind in ("passive", "connector"):
            continue
        for n in (n for n in d.p.nodes if n.ref == part.ref):
            hp = d.p.host_pin(n.net)
            if hp and hp.type == "gpio" and n.net != netlist.NC_NET:
                print(f"{part.ref:<5}{part.function[:33]:<34}{n.pin:<6}{n.net:<12}{hp.bcm:>5}{hp.pin:>5}")


# ----------------------------------------------------------------------------- pull-ups

def check_pullups(r: Report, d: Design) -> None:
    """With the Pi's internal pull-DOWN on, a line reads high only if the external pull-up exists."""
    from gpiozero import DigitalInputDevice

    lines: list[tuple[str, str]] = []
    tcs = d.parts_like("MAX31856")
    for part in tcs:
        lines.append((part.ref, d.p.net_of(part.ref, "CS") or ""))
    for part in d.parts_like("ADS1115"):
        lines.append((part.ref, d.p.net_of(part.ref, "ALRT") or ""))
    for ref, net in lines:
        if net == netlist.NC_NET:
            continue                                        # deliberately not wired
        g = d.net_gpio(net)
        if g is None:
            r.fail(ref, f"{net or '?'}: no header GPIO in netlist")
            continue
        with DigitalInputDevice(g, pull_up=False) as pin:
            time.sleep(0.005)
            level = pin.value
        if level:
            r.ok(ref, f"{net} (GPIO{g}) idles high: pull-up present")
        else:
            r.fail(ref, f"{net} (GPIO{g}) reads low against the internal pull-down: "
                        f"pull-up missing, line shorted to GND, or a module holds it low")


# ----------------------------------------------------------------------------- I2C

def check_icm20948(r: Report, bus, part: netlist.Part, int_gpio: int | None) -> None:
    a = part.i2c_addr
    try:
        bus.write_byte_data(a, 0x7F, 0x00)                  # REG_BANK_SEL = bank 0
        who = bus.read_byte_data(a, 0x00)                   # WHO_AM_I
    except OSError as e:
        r.fail(part.ref, f"ICM-20948: no ACK at 0x{a:02X} ({e})")
        return
    if who != 0xEA:
        r.fail(part.ref, f"ICM-20948: WHO_AM_I=0x{who:02X}, expected 0xEA")
        return
    r.ok(part.ref, f"ICM-20948 at 0x{a:02X}: WHO_AM_I=0xEA")

    bus.write_byte_data(a, 0x06, 0x01)                      # PWR_MGMT_1: wake, auto clock
    time.sleep(0.05)
    bus.write_byte_data(a, 0x03, bus.read_byte_data(a, 0x03) & ~0x20 & 0xFF)  # USER_CTRL: I2C_MST_EN=0
    bus.write_byte_data(a, 0x0F, 0x22)                      # INT_PIN_CFG: LATCH_EN | BYPASS_EN, active high
    time.sleep(0.01)
    try:
        wia = bus.read_i2c_block_data(0x0C, 0x00, 2)        # AK09916 WIA1, WIA2
        if wia == [0x48, 0x09]:
            r.ok(part.ref, "AK09916 magnetometer answers at 0x0C (bypass mode)")
        else:
            r.fail(part.ref, f"AK09916 WIA={wia}, expected [0x48, 0x09]")
    except OSError:
        r.fail(part.ref, "AK09916 magnetometer not answering at 0x0C in bypass mode")

    raw = bus.read_i2c_block_data(a, 0x2D, 6)               # ACCEL_XOUT_H..ACCEL_ZOUT_L, +/-2 g default
    ax, ay, az = (s16(raw[i], raw[i + 1]) / 16384 for i in (0, 2, 4))
    g = math.sqrt(ax * ax + ay * ay + az * az)
    msg = f"|a|={g:.2f} g (x={ax:+.2f} y={ay:+.2f} z={az:+.2f})"
    (r.ok if 0.8 < g < 1.2 else r.warn)(part.ref, msg + ("" if 0.8 < g < 1.2 else " - expected ~1 g at rest"))

    if int_gpio is None:
        r.skip(part.ref, "IMU INT not wired to a header GPIO")
        return
    from gpiozero import DigitalInputDevice
    with DigitalInputDevice(int_gpio, pull_up=False) as pin:
        try:
            bus.write_byte_data(a, 0x11, 0x00)              # INT_ENABLE_1: data-ready off
            bus.read_byte_data(a, 0x1A)                     # INT_STATUS_1: clears the latch
            time.sleep(0.01)
            idle = pin.value
            bus.write_byte_data(a, 0x11, 0x01)              # RAW_DATA_0_RDY_EN
            time.sleep(0.02)
            active = pin.value
        finally:
            bus.write_byte_data(a, 0x11, 0x00)
            bus.read_byte_data(a, 0x1A)
    if (idle, active) == (0, 1):
        r.ok(part.ref, f"INT -> GPIO{int_gpio}: low when idle, high on data-ready")
    else:
        r.fail(part.ref, f"INT on GPIO{int_gpio}: idle={idle} active={active}, expected 0 then 1")


def check_bme680(r: Report, bus, part: netlist.Part) -> None:
    for a in [part.i2c_addr] + [x for x in (0x76, 0x77) if x != part.i2c_addr]:
        try:
            cid = bus.read_byte_data(a, 0xD0)
        except OSError:
            continue
        if cid != 0x61:
            r.fail(part.ref, f"chip id 0x{cid:02X} at 0x{a:02X}: not a BME680 "
                             f"(0x61=BME680/688, 0x60=BME280, 0x58=BMP280)")
        elif a == part.i2c_addr:
            r.ok(part.ref, f"BME680 at 0x{a:02X}: chip id 0x61")
        else:
            r.warn(part.ref, f"BME680 found at 0x{a:02X} but parts.csv says 0x{part.i2c_addr:02X}: "
                             f"update i2c_addr and run `make docs`")
        return
    r.fail(part.ref, "BME680: no ACK at 0x76 or 0x77")


def check_ms4525(r: Report, bus, i2c_msg, part: netlist.Part) -> None:
    a = part.i2c_addr
    try:
        msg = i2c_msg.read(a, 4)                            # Read_DF4: status, pressure, temperature
        bus.i2c_rdwr(msg)
        b = list(msg)
    except OSError as e:
        r.fail(part.ref, f"MS4525DO: no ACK at 0x{a:02X} ({e}); check the part's interface code "
                         f"(I=0x28, J=0x36, K=0x46)")
        return
    status = b[0] >> 6
    counts = ((b[0] & 0x3F) << 8) | b[1]
    temp = (((b[2] << 8) | b[3]) >> 5) * 200.0 / 2047 - 50
    if status == 3:
        r.fail(part.ref, "MS4525DO status=3 (sensor fault)")
        return
    msg = f"MS4525DO at 0x{a:02X}: status={status} pressure={counts} counts T={temp:.1f} C"
    if status == 2:
        r.warn(part.ref, msg + " - stale data (a low-power -L/-M part needs a measurement request first)")
    elif not 0 <= temp <= 70:
        r.warn(part.ref, msg + " - temperature implausible")
    elif abs(counts - 8192) > 0.05 * 16383:
        r.warn(part.ref, msg + " - far from mid-scale 8192; are both ports open to ambient?")
    else:
        r.ok(part.ref, msg)


def check_ads1115(r: Report, bus, part: netlist.Part, alrt_gpio: int | None) -> None:
    a = part.i2c_addr

    def rd(reg: int) -> int:
        hi, lo = bus.read_i2c_block_data(a, reg, 2)
        return (hi << 8) | lo

    def wr(reg: int, val: int) -> None:
        bus.write_i2c_block_data(a, reg, [val >> 8, val & 0xFF])

    try:
        cfg = rd(0x01)
    except OSError as e:
        r.fail(part.ref, f"ADS1115: no ACK at 0x{a:02X} ({e})")
        return
    note = "power-on default" if cfg == 0x8583 else "changed since power-up"
    r.ok(part.ref, f"ADS1115 at 0x{a:02X}: config=0x{cfg:04X} ({note})")

    from gpiozero import DigitalInputDevice
    pin = DigitalInputDevice(alrt_gpio, pull_up=False) if alrt_gpio is not None else None
    idle = after = None
    volts = []
    try:
        wr(0x01, 0x0583)                                    # defaults, COMP_QUE=11: ALERT/RDY high-Z
        time.sleep(0.01)
        idle = pin.value if pin else None
        wr(0x02, 0x0000)                                    # Lo_thresh MSB=0 and Hi_thresh MSB=1:
        wr(0x03, 0x8000)                                    # ALERT/RDY becomes conversion-ready
        for ch in range(4):
            # OS | MUX=AINch vs GND | PGA +/-6.144 V (ems-adc.json gain_mv 6144) | single-shot | 128 SPS
            wr(0x01, 0x8000 | ((4 + ch) << 12) | (0 << 9) | (1 << 8) | (4 << 5))
            t0 = time.monotonic()
            while not rd(0x01) & 0x8000:                    # OS reads 1 once the conversion is done
                if time.monotonic() - t0 > 0.1:
                    raise TimeoutError("conversion did not finish")
                time.sleep(0.002)
            if ch == 0 and pin:
                after = pin.value
            raw = rd(0x00)
            volts.append((raw - 0x10000 if raw & 0x8000 else raw) * 6.144 / 32768)
    except (OSError, TimeoutError) as e:
        r.fail(part.ref, f"ADS1115 conversion failed: {e}")
        return
    finally:
        try:
            wr(0x02, 0x8000)                                # restore threshold and config defaults
            wr(0x03, 0x7FFF)
            wr(0x01, 0x0583)
        except OSError:
            pass
        if pin:
            pin.close()
    r.ok(part.ref, "A0..A3 = " + "  ".join(f"{v:.3f} V" for v in volts) + " (floating inputs read noise)")
    if pin is None:
        r.skip(part.ref, "ALERT/RDY not wired to a header GPIO")
    elif (idle, after) == (1, 0):
        r.ok(part.ref, f"ALERT/RDY -> GPIO{alrt_gpio}: high when disabled, low after a conversion")
    else:
        r.fail(part.ref, f"ALERT/RDY on GPIO{alrt_gpio}: disabled={idle} after-conversion={after}, "
                         f"expected 1 then 0")


def check_i2c(r: Report, d: Design) -> None:
    from smbus2 import SMBus, i2c_msg

    buses: dict[str, SMBus] = {}

    def bus(part: netlist.Part) -> SMBus:                   # one handle per I2C bus (I2C0, I2C1)
        if part.bus not in buses:
            buses[part.bus] = SMBus(int(part.bus.removeprefix("I2C")))
        return buses[part.bus]

    try:
        for part in d.parts_like("ICM-20948"):
            check_icm20948(r, bus(part), part, d.gpio(part.ref, "INT"))
        for part in d.parts_like("BME680"):
            check_bme680(r, bus(part), part)
        for part in d.parts_like("MS4525DO"):
            check_ms4525(r, bus(part), i2c_msg, part)
        for part in d.parts_like("ADS1115"):
            check_ads1115(r, bus(part), part, d.gpio(part.ref, "ALRT"))
    finally:
        for b in buses.values():
            b.close()


# ----------------------------------------------------------------------------- MAX31856

class Thermocouple:
    def __init__(self, spi, part: netlist.Part, gpio: int) -> None:
        from gpiozero import DigitalOutputDevice

        self.spi, self.part, self.gpio = spi, part, gpio
        self.name = tc_name(part)
        self.cs = DigitalOutputDevice(gpio, active_high=True, initial_value=True)  # high = deselected

    def xfer(self, data: list[int]) -> list[int]:
        self.cs.off()
        try:
            return self.spi.xfer2(list(data))
        finally:
            self.cs.on()

    def read(self, reg: int, n: int = 1) -> list[int]:
        return self.xfer([reg & 0x7F] + [0] * n)[1:]

    def write(self, reg: int, *vals: int) -> None:
        self.xfer([reg | 0x80, *vals])

    def close(self) -> None:
        self.cs.close()


def check_tc(r: Report, d: Design, tc_type: str) -> None:
    parts = d.parts_like("MAX31856")
    if not parts:
        r.skip("TC", "no MAX31856 in the fitted set")
        return
    by_bus: dict[str, list[netlist.Part]] = {}
    for part in parts:
        by_bus.setdefault(part.bus, []).append(part)
    for bus, group in sorted(by_bus.items()):
        check_tc_bus(r, d, bus, group, tc_type)


def check_tc_bus(r: Report, d: Design, bus: str, parts: list[netlist.Part], tc_type: str) -> None:
    import spidev

    spi = spidev.SpiDev()
    spi.open(int(bus.removeprefix("SPI")), 0)
    spi.max_speed_hz = SPI_HZ
    spi.mode = SPI_MODE
    tcs: list[Thermocouple] = []
    try:
        for part in parts:                                  # every CS is driven high before any transfer
            g = d.gpio(part.ref, "CS")
            if g is None:
                r.fail(part.ref, f"{tc_name(part)}: CS has no header GPIO in netlist")
                continue
            try:
                tcs.append(Thermocouple(spi, part, g))
            except Exception as e:                          # e.g. line held by the kernel SPI driver
                r.fail(part.ref, f"{tc_name(part)}: cannot drive CS GPIO{g} ({e}). GPIO7/8 need "
                                 f"dtoverlay=spi0-0cs instead of dtparam=spi=on")

        # 1. Identity: unique value in CJTO (cold-junction offset) per chip, then read all back.
        tags = {tc: 0x10 + i for i, tc in enumerate(tcs)}
        for tc, tag in tags.items():
            tc.write(0x09, tag)
        good = []
        for tc, tag in tags.items():
            got = tc.read(0x09)[0]
            where = f"{tc.name} (CS GPIO{tc.gpio})"
            if got == tag:
                good.append(tc)
                r.ok(tc.part.ref, f"{where}: responds; CR1=0x{tc.read(0x01)[0]:02X}")
            elif got == 0xFF:
                r.fail(tc.part.ref, f"{where}: reads 0xFF - no chip on this CS, module unpowered, "
                                    f"or MISO not connected")
            elif got == 0x00:
                r.fail(tc.part.ref, f"{where}: reads 0x00 - MISO stuck low or module unpowered")
            elif got in tags.values():
                other = next(t.name for t, v in tags.items() if v == got)
                r.fail(tc.part.ref, f"{where}: returns {other}'s value - its CS is shorted to {other}'s CS")
            else:
                r.fail(tc.part.ref, f"{where}: read 0x{got:02X}, expected 0x{tag:02X} - bus contention "
                                    f"(a module SDO not tri-stating?) or noise")
        for tc in tcs:
            tc.write(0x09, 0x00)

        # 2. One conversion on every responding chip.
        for tc in good:
            tc.write(0x00, 0x01)                            # CR0: normally-off, 50 Hz notch (Europe)
            tc.write(0x01, TC_TYPES[tc_type])               # CR1: 1 sample, thermocouple type
            tc.write(0x02, 0xFF)                            # MASK: all faults masked
            tc.write(0x00, 0x51)                            # CR0: 1SHOT | OCFAULT=01 | 50 Hz
        time.sleep(0.35)                                    # > 185 ms conversion + open-circuit test
        for tc in good:
            b = tc.read(0x0A, 6)                            # CJTH CJTL LTCBH LTCBM LTCBL SR
            cj = s16(b[0], b[1]) / 256.0
            ltc = (b[2] << 16) | (b[3] << 8) | b[4]
            ltc = ((ltc - (1 << 24)) if ltc & 0x800000 else ltc) >> 5
            temp, sr = ltc * 0.0078125, b[5]
            faults = [name for bit, name in enumerate(SR_BITS) if sr & (1 << bit)]
            msg = f"{tc.name}: cold junction {cj:.2f} C"
            if not 5 <= cj <= 85:
                r.warn(tc.part.ref, msg + " - implausible board temperature")
            elif sr & 0x01:
                r.warn(tc.part.ref, msg + ", thermocouple OPEN (nothing connected?)")
            elif faults:
                r.warn(tc.part.ref, msg + f", type {tc_type} {temp:.2f} C, faults: {', '.join(faults)}")
            else:
                r.ok(tc.part.ref, msg + f", type {tc_type} {temp:.2f} C")
    finally:
        for tc in tcs:
            tc.close()
        spi.close()


# ----------------------------------------------------------------------------- main

def check_platform(r: Report, d: Design, cmd: str) -> bool:
    model = Path("/proc/device-tree/model")
    text = model.read_text(errors="ignore").strip("\x00\n") if model.exists() else "not a Raspberry Pi"
    (r.ok if "Raspberry Pi 5" in text else r.warn)("host", text)
    kinds = {"i2c": ("I2C",), "tc": ("SPI",), "all": ("I2C", "SPI")}.get(cmd, ())
    buses = sorted({d.p.parts[ref].bus for ref in d.fitted if d.p.parts[ref].bus.startswith(kinds)}
                   if kinds else set())
    needed = [BUS_DEVICES[b] for b in buses if b in BUS_DEVICES]
    missing = [(dev, fix) for dev, fix in needed if not Path(dev).exists()]
    for dev, fix in missing:
        r.fail("host", f"{dev} missing: add '{fix}' to /boot/firmware/config.txt and reboot")
    return not missing


def main() -> int:
    ap = argparse.ArgumentParser(description="RB01HAT bring-up / wiring verification")
    ap.add_argument("cmd", choices=["pins", "pullups", "i2c", "tc", "all"])
    ap.add_argument("--fitted", help="comma-separated refs mounted so far (default: all non-DNP parts)")
    ap.add_argument("--tc-type", default="K", choices=sorted(TC_TYPES), help="thermocouple type (default K)")
    args = ap.parse_args()

    d = Design(args.fitted)
    if args.cmd == "pins":
        print_pins(d)
        return 0
    r = Report()
    if check_platform(r, d, args.cmd):
        if args.cmd in ("pullups", "all"):
            check_pullups(r, d)
        if args.cmd in ("i2c", "all"):
            check_i2c(r, d)
        if args.cmd in ("tc", "all"):
            check_tc(r, d, args.tc_type)
    return r.summary()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generate docs/generated/rb01-system.svg - the RB-01 high-level system diagram.

Edit the component lists below, then run `make docs` (or `python3 tools/rb01_diagram.py`).
The layout is fixed; the script warns when a label is too long for its box.
Standard library only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "rb01-system.svg"
W, H = 1680, 1100
FONT = "Inter, 'Segoe UI', 'Helvetica Neue', Arial, 'DejaVu Sans', sans-serif"
INK, MUTED, FAINT = "#0f172a", "#475569", "#94a3b8"

# Interface type -> (colour, dash pattern, legend label)
LINK = {
    "video": ("#9333ea", "", "HDMI / DSI video"),
    "gpio": ("#d97706", "", "GPIO header: I2C, SPI, UART"),
    "usb": ("#2563eb", "", "USB"),
    "pcie": ("#0d9488", "", "PCIe"),
    "eth": ("#65a30d", "", "Ethernet"),
    "bt": ("#4338ca", "7 5", "Bluetooth"),
    "wifi": ("#0891b2", "7 5", "Wi-Fi"),
    "power": ("#dc2626", "", "5 V power"),
    "internet": ("#64748b", "2 5", "Internet path"),
}

# ----------------------------------------------------------------------------- components

DISPLAYS = [  # (title, details) - top to bottom, matching Pi ports HDMI0, HDMI1, DSI
    ("Primary display", ["Waveshare 8″ HDMI", "touch: USB via the panel keypad hub"]),
    ("Secondary display", ["80 mm round HDMI", "touch: USB via the panel keypad hub"]),
    ("Third display", ["Waveshare 7″ rectangular DSI", "touch: I2C over the DSI cable"]),
]
EMS = ("EMS sensors", [
    "CHT 1–4 · EGT 1–4 (MAX31856 ×8, SPI1 / SPI0)",
    "Oil temp/press., fuel, battery (ADS1115, I2C0)",
    "RPM pickup (GPIO22)",
])
AHRS = ("AHRS with magnetometer", [
    "ICM-20948 IMU + AK09916 mag (I2C1)",
    "Air data: MS4525DO airspeed, BME680",
])
GEAR = ("Landing gear sensors", ["Nose / left / right switches", "GPIO25 · GPIO12 · GPIO16"])
GPS = ("GPS u-blox M10", ["Serial NMEA / UBX (UART0)", "GPIO14 TX · GPIO15 RX"])
FLARM_OUT = ("FLARM OUT → traffic annunciators", ["Multiple annunciators, serial", "UART2 TX on GPIO4"])
UPS = ("Battery backup HAT (UPS)", "5 V USB-C output")
USB_HAT = ("USB expansion HAT", "PCIe-to-USB controller")
USB_LOCAL = [  # first entry links to the remote hub
    ("USB cable to remote hub", "remote USB expansion"),
    ("RB-07", "traffic display + backup attitude (direct USB)"),
    ("USB-RS232 → KRT2 radio", "radio control"),
    ("USB-RS232 → FLARM display + Garmin G5", "NMEA, 9600 baud"),
    ("USB-CAN → Garmin CAN bus", "CAN interface"),
    ("USB audio card", "comm integration"),
    ("USB storage", "flight log + audio recorder"),
    ("USB panel keypad + hub", "knob · hub for the HDMI displays' touch"),
]
REMOTE = [  # last entry is the internet source for Wi-Fi sharing
    ("RTL-SDR #1", "1090 MHz ADS-B"),
    ("RTL-SDR #2", "VOR"),
    ("T-Beam", "ADS-L TX/RX"),
    ("LTE / 5G modem", "internet uplink"),
]
ETHERNET = [("RB-06", "wired Ethernet link")]
BLUETOOTH = [("Joystick", "navigation commands"), ("Secondary radio", "BLE-RS232 adapter")]
WIFI = [("Tablet", "GDL90"), ("Internet sharing", "via the LTE / 5G modem"), ("Remote GUI", "browser access")]


# ----------------------------------------------------------------------------- drawing helpers

class Svg:
    def __init__(self) -> None:
        self.body: list[str] = []
        self.warnings: list[str] = []

    def add(self, s: str) -> None:
        self.body.append(s)

    def fits(self, text: str, size: float, bold: bool, width: float) -> None:
        est = len(text) * size * (0.58 if bold else 0.5)
        if est > width:
            self.warnings.append(f"label may overflow ({est:.0f} > {width:.0f} px): {text}")

    def text(self, x: float, y: float, t: str, size: float = 12, weight: str = "normal", fill: str = INK,
             anchor: str = "start", halo: bool = False) -> None:
        extra = ' paint-order="stroke" stroke="#ffffff" stroke-width="4" stroke-linejoin="round"' if halo else ""
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
                 f'text-anchor="{anchor}"{extra}>{escape(t)}</text>')

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str, rx: float = 8,
             dash: str = "", sw: float = 1.2) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def group(self, x: float, y: float, w: float, h: float, label: str, tint: str, border: str,
              dash: str = "") -> None:
        self.rect(x, y, w, h, tint, border, rx=12, dash=dash)
        self.text(x + 14, y + 19, label.upper(), size=11, weight="700", fill=MUTED)

    def card(self, x: float, y: float, w: float, h: float, title: str, lines: list[str] | tuple[str, ...] = (),
             border: str = "#cbd5e1") -> None:
        self.rect(x, y, w, h, "#ffffff", border)
        self.fits(title, 13, True, w - 20)
        self.text(x + 10, y + 20, title, size=13, weight="600")
        for i, line in enumerate(lines):
            self.fits(line, 11.5, False, w - 20)
            self.text(x + 10, y + 37 + 15 * i, line, size=11.5, fill=MUTED)

    def link(self, pts: list[tuple[float, float]], kind: str, arrow: bool = False, sw: float = 2.5) -> None:
        color, dash, _ = LINK[kind]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#arrow-{kind})"' if arrow else ""
        p = " ".join(f"{x},{y}" for x, y in pts)
        self.add(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}" '
                 f'stroke-linecap="round" stroke-linejoin="round"{d}{m}/>')

    def port(self, x: float, y: float, kind: str) -> None:
        self.add(f'<circle cx="{x}" cy="{y}" r="4.5" fill="#ffffff" stroke="{LINK[kind][0]}" stroke-width="2.5"/>')

    def render(self) -> str:
        markers = "".join(
            f'<marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            for k, (c, _, _) in LINK.items())
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
                f'font-family="{FONT}">\n<title>RB-01 high-level system diagram</title>\n'
                f'<defs>{markers}</defs>\n<rect width="{W}" height="{H}" fill="#ffffff"/>\n'
                + "\n".join(self.body) + "\n</svg>\n")


# ----------------------------------------------------------------------------- layout

def build() -> Svg:
    s = Svg()
    s.text(30, 38, "RB-01 — high-level system diagram", size=22, weight="700")
    s.text(30, 60, "Raspberry Pi 5 core with the RB01HAT on the GPIO header · logical data links only · "
                   "generated by tools/rb01_diagram.py", size=12, fill=MUTED)

    # Raspberry Pi 5 (ports: left = video + power, top = GPIO, right = USB + PCIe, bottom = network/radio)
    px, py, pw, ph = 430, 390, 300, 410
    s.rect(px, py, pw, ph, "#0f172a", "#0f172a", rx=14)
    s.text(px + pw / 2, 412, "40-pin GPIO header", size=11, fill="#cbd5e1", anchor="middle")
    for y, label in ((434, "HDMI0"), (524, "HDMI1"), (614, "MIPI DSI"), (728, "USB-C 5 V in")):
        s.text(px + 14, y, label, size=11, fill="#cbd5e1")
    s.text(px + pw - 12, 464, "USB 3.0 ×2 · USB 2.0 ×2", size=11, fill="#cbd5e1", anchor="end")
    s.text(px + pw - 12, 604, "PCIe FFC", size=11, fill="#cbd5e1", anchor="end")
    for x, label in ((480, "Ethernet"), (580, "Bluetooth"), (680, "Wi-Fi")):
        s.text(x, 786, label, size=11, fill="#cbd5e1", anchor="middle")
    s.text(px + pw / 2, 652, "Raspberry Pi 5", size=26, weight="700", fill="#ffffff", anchor="middle")
    s.text(px + pw / 2, 676, "RB-01 core", size=13, fill="#cbd5e1", anchor="middle")
    s.text(px + pw / 2, 694, "RB-01 software · rb-ems-go daemons", size=11.5, fill=FAINT, anchor="middle")

    # GPIO header: RB01HAT (EMS + AHRS) and the directly wired sensors
    s.group(300, 76, 660, 262, "40-pin GPIO header", "#fffbeb", "#fcd34d")
    s.group(315, 104, 330, 222, "RB01HAT (sensor HAT)", "#fef3c7", "#f59e0b", dash="5 4")
    s.card(330, 130, 300, 88, EMS[0], EMS[1])
    s.card(330, 228, 300, 86, AHRS[0], AHRS[1])
    s.card(660, 104, 285, 66, GEAR[0], GEAR[1])
    s.card(660, 182, 285, 66, GPS[0], GPS[1])
    s.card(660, 260, 285, 66, FLARM_OUT[0], FLARM_OUT[1])
    s.link([(580, py), (580, 338)], "gpio", sw=4)
    s.port(580, py, "gpio")

    # Displays and power (left)
    s.group(30, 370, 310, 292, "Displays", "#faf5ff", "#d8b4fe")
    for i, (title, details) in enumerate(DISPLAYS):
        cy = 430 + 90 * i
        s.card(45, cy - 30, 280, 72, title, details)
        s.link([(325, cy), (px, cy)], "video")
        s.port(px, cy, "video")
    s.group(30, 670, 310, 98, "Power", "#fef2f2", "#fca5a5")
    s.card(45, 696, 280, 56, UPS[0], [UPS[1]])
    s.link([(325, 724), (px - 6, 724)], "power", arrow=True)

    # USB: native ports and the PCIe USB HAT feed the local USB devices
    bus_x = 1050
    s.link([(px + pw, 460), (bus_x, 460)], "usb")
    s.port(px + pw, 460, "usb")
    s.link([(px + pw, 600), (790, 600)], "pcie")
    s.port(px + pw, 600, "pcie")
    s.card(790, 566, 210, 68, USB_HAT[0], [USB_HAT[1]])
    s.link([(1000, 600), (bus_x, 600)], "usb")
    s.group(1075, 340, 340, 515, "USB local devices", "#eff6ff", "#93c5fd")
    ys = [395 + 60 * i for i in range(len(USB_LOCAL))]
    s.link([(bus_x, ys[0]), (bus_x, ys[-1])], "usb", sw=3)
    for cy, (title, detail) in zip(ys, USB_LOCAL):
        s.link([(bus_x, cy), (1090, cy)], "usb")
        s.card(1090, cy - 25, 310, 50, title, [detail])

    # Remote hub (right), linked from the first local USB entry
    s.group(1440, 340, 225, 270, "Remote USB hub", "#eff6ff", "#93c5fd", dash="6 4")
    s.link([(1400, ys[0]), (1440, ys[0])], "usb")
    for i, (title, detail) in enumerate(REMOTE):
        s.card(1452, 370 + 56 * i, 200, 48, title, [detail])
    lte_bottom = 370 + 56 * (len(REMOTE) - 1) + 48

    # Network and radios (bottom)
    s.group(290, 880, 210, 190, "Ethernet", "#f0fdf4", "#86efac")
    for i, (title, detail) in enumerate(ETHERNET):
        s.card(302, 912 + 58 * i, 186, 50, title, [detail])
    s.group(520, 880, 270, 190, "Bluetooth", "#eef2ff", "#a5b4fc")
    for i, (title, detail) in enumerate(BLUETOOTH):
        s.card(532, 912 + 58 * i, 246, 50, title, [detail])
    s.group(810, 880, 270, 190, "Wi-Fi", "#ecfeff", "#67e8f9")
    for i, (title, detail) in enumerate(WIFI):
        s.card(822, 912 + 50 * i, 246, 44, title, [detail])
    s.link([(480, py + ph), (480, 848), (395, 848), (395, 880)], "eth")
    s.link([(580, py + ph), (580, 848), (655, 848), (655, 880)], "bt")
    s.link([(680, py + ph), (680, 832), (945, 832), (945, 880)], "wifi")
    for x, kind in ((480, "eth"), (580, "bt"), (680, "wifi")):
        s.port(x, py + ph, kind)

    # Internet path: LTE / 5G modem -> Wi-Fi internet sharing
    share_y = 912 + 50 * 1 + 22
    s.link([(1552, lte_bottom), (1552, share_y), (1074, share_y)], "internet", arrow=True, sw=2)
    s.text(1310, share_y - 8, "internet: LTE / 5G modem → shared over Wi-Fi", size=11.5, fill=MUTED,
           anchor="middle", halo=True)

    # Legend
    s.group(30, 790, 240, 280, "Legend", "#f8fafc", "#cbd5e1")
    for i, (kind, (_, _, label)) in enumerate(LINK.items()):
        y = 826 + 26 * i
        s.link([(45, y), (85, y)], kind, arrow=kind in ("power", "internet"))
        s.text(95, y + 4, label, size=11.5, fill=INK)

    s.text(290, 1090, "Not shown: harness, grounding, mechanical stacking. Each peripheral has its own power supply.",
           size=11, fill=FAINT)
    return s


def main() -> int:
    s = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(s.render(), encoding="utf-8")
    for w in s.warnings:
        print(f"WARN  {w}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

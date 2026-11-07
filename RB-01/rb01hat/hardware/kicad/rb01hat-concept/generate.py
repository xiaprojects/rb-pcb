#!/usr/bin/env python3
"""Generate the RB01HAT Rev A CONCEPT board, then route it, run the DRC and render it.

This is a visualisation of docs/06-custom-pcb.md, not a released design: see README.md.

    python3 generate.py            # board + routing + DRC
    python3 generate.py --render   # the same, then the JPG renders

Run it with the system Python that has KiCad 9's pcbnew module.

Sources:
  hardware/netlist.csv   nets and refdes; every row is checked against the placed pads
  docs/06-custom-pcb.md  chips, outline A (HAT+ 65 x 56.5 mm), 4-layer stack
  docs/03-mechanical.md  zones Z1-Z6
Pin tables come from the datasheets listed in docs/references.md.
"""
import csv
import ctypes
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("RB01HAT_ROOT", HERE.parents[2]))
NAME = "rb01hat-concept"
PCB = HERE / f"{NAME}.kicad_pcb"
PRO = HERE / f"{NAME}.kicad_pro"
LIB = HERE / "lib" / "RB01HAT.pretty"
MODELS = HERE / "3dmodels"
RENDERS = HERE / "renders"
FP = "/usr/share/kicad/footprints"
MASK = "#7E0F16F2"       # deep red: same family as the Rev 0 proto HAT, and the tracks stay readable
MODEL_URL = "https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/master"
# KiCad's library has no VSSOP-10 model; MSOP-10 is the same 3 x 3 mm 0.5 mm pitch outline.
MODEL_STANDIN = {"VSSOP-10_3x3mm_P0.5mm.step": "Package_SO.3dshapes/MSOP-10_3x3mm_P0.5mm.step"}

W, H = 65.0, 56.5        # HAT+ outline, doc 06 option A
OX, OY = 100.0, 40.0     # board origin on the sheet
G = 0.1                  # routing grid
TW, CL = 0.16, 0.13      # track width, clearance
VD, VDRL = 0.6, 0.3      # via
MARGIN = 0.03            # raster margin added to every clearance
EDGE = 0.35              # copper to board edge
NX, NY = int(round(W / G)) + 1, int(round(H / G)) + 1
PLANE_NETS = {"GND", "3V3"}   # In1 = GND, In2 = 3V3; every other net is routed on F.Cu / B.Cu


def mm(v):
    return pcbnew.FromMM(v)


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def rel(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


# ------------------------------------------------------------------ placement
R0603 = ("Resistor_SMD", "R_0603_1608Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
C1206 = ("Capacitor_SMD", "C_1206_3216Metric")
SOIC8 = ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")
TSSOP14 = ("Package_SO", "TSSOP-14_4.4x5mm_P0.65mm")
SSOP8 = ("Package_SO", "SSOP-8_2.95x2.8mm_P0.65mm")
VSSOP10 = ("Package_SO", "VSSOP-10_3x3mm_P0.5mm")
SOT235 = ("Package_TO_SOT_SMD", "SOT-23-5")
QFN24 = ("Package_DFN_QFN", "QFN-24-1EP_3x3mm_P0.4mm_EP1.75x1.6mm")
LGA8 = ("Package_LGA", "Bosch_LGA-8_3x3mm_P0.8mm_ClockwisePinNumbering")
TB2 = ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal")
TB5 = ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_PT-1,5-5-3.5-H_1x05_P3.50mm_Horizontal")
IDC10 = ("Connector_IDC", "IDC-Header_2x05_P2.54mm_Vertical")
TP = ("TestPoint", "TestPoint_Pad_D1.5mm")
HOLE = ("MountingHole", "MountingHole_2.7mm_M2.5")
SOCKET = ("Connector_PinSocket_2.54mm", "PinSocket_2x20_P2.54mm_Vertical")

CX = [27.0, 37.16, 47.32, 57.48]        # CHT columns, 10.16 mm pitch (doc 03 zone Z3)

# ref: (footprint, value, x, y, rotation)   rotation: KiCad degrees, counter-clockwise
PARTS = {
    # Z3: CHT bank. Analog side of each MAX31856 faces its terminal, SPI side faces away.
    **{f"U{3 + i}": (TSSOP14, "MAX31856", CX[i], 21.8, 270) for i in range(4)},
    **{f"J{3 + i}": (TB2, f"CHT{i + 1}", CX[i] + 1.75, 11.9, 180) for i in range(4)},
    **{f"R{1 + i}": (R0603, "10k", CX[i] - 3.8, 26.8, 0) for i in range(4)},
    **{f"C{4 + 3 * i}": (C0603, "100n", CX[i] - 3.8, 20.1, 90) for i in range(4)},   # AVDD
    **{f"C{5 + 3 * i}": (C0603, "100n", CX[i] - 3.8, 23.8, 90) for i in range(4)},   # DVDD
    **{f"C{6 + 3 * i}": (C0603, "100n", CX[i] + 0.3, 16.7, 0) for i in range(4)},    # T+ to T-
    # Z1: IMU, its 1.8 V LDO and translator
    "U1": (QFN24, "ICM-20948", 9.0, 12.2, 270),
    "U15": (SSOP8, "PCA9306", 16.8, 12.2, 0),
    "U16": (SOT235, "AP2112K-1.8", 7.8, 19.4, 0),
    "C16": (C0603, "100n", 8.6, 15.8, 0),      # VDD
    "C17": (C0603, "100n", 4.4, 10.6, 180),    # VDDIO
    "C18": (C0603, "100n", 4.4, 12.4, 180),    # REGOUT
    "C19": (C0603, "1u", 4.4, 19.4, 90),       # LDO in
    "C20": (C0603, "1u", 11.2, 19.4, 90),      # LDO out
    "C21": (C0603, "100p", 21.3, 14.2, 90),    # translator EN
    "R14": (R0603, "200k", 21.3, 11.0, 90),    # translator EN
    "R15": (R0603, "2k2", 15.0, 16.2, 0),
    "R16": (R0603, "2k2", 18.6, 16.2, 0),
    # rail entry and ID EEPROM
    "C1": (C1206, "22u", 19.4, 7.6, 0),
    "C2": (C0603, "100n", 15.4, 7.5, 0),
    "U13": (SOIC8, "CAT24C32", 17.6, 21.6, 0),
    "R13": (R0603, "1k", 11.8, 23.2, 0),
    "TP1": (TP, "WP", 11.8, 25.6, 0),
    "R11": (R0603, "3k9", 16.2, 26.6, 0),
    "R12": (R0603, "3k9", 19.4, 26.6, 0),
    # Z2: BME680 on its milled peninsula
    "U2": (LGA8, "BME680", 4.6, 32.2, 180),
    "C22": (C0603, "100n", 8.3, 32.2, 90),
    # Z4: MS4525DO, ports over the left edge
    "U7": (("RB01HAT", "MS4525DO_DS_DIP-8"), "MS4525DO", 12.45, 45.5, 0),
    "C3": (C0603, "100n", 12.9, 54.2, 0),
    # Z5: ADC, translator, field terminal
    "U8": (VSSOP10, "ADS1115", 30.6, 40.4, 0),
    "U14": (SSOP8, "PCA9306", 38.0, 39.2, 180),
    "C23": (C0603, "100n", 30.6, 36.6, 0),
    "C24": (C0603, "100n", 41.8, 39.2, 90),
    "C25": (C0603, "100p", 34.2, 35.6, 0),
    "R17": (R0603, "10k", 37.4, 35.6, 0),
    "R18": (R0603, "10k", 40.6, 35.6, 0),
    "R19": (R0603, "200k", 34.2, 33.8, 0),
    "J2": (TB5, "ADC IN", 26.0, 51.2, 0),
    **{f"R{20 + i}": (R0603, "1k", 26.0 + 3.5 * i, 45.8, 90) for i in range(4)},
    **{f"C{26 + i}": (C0603, "100n", 27.6 + 3.5 * i, 45.8, 90) for i in range(4)},
    # Z6: EGT ribbon, CS pull-ups on the HAT side
    "J11": (IDC10, "EGT ribbon", 60.0, 43.6, 180),
    **{f"R{5 + i}": (R0603, "10k", 50.6, 32.2 + 2.0 * i, 0) for i in range(4)},
}
HOLES = {"H1": (3.5, 3.5), "H2": (61.5, 3.5), "H3": (3.5, 52.5), "H4": (61.5, 52.5)}
J1_PIN1 = (8.37, 4.77)   # header centred between the holes: 3.5 + 29 from the board corner

# Where a netlist pin ends up on the Rev A chip. Every pin table below was read from the part's datasheet:
#   MAX31856 (TSSOP), ICM-20948 (table 10), MS4525DO (p.7), ADS1115, PCA9306 (DCT package),
#   BME680 (table 20), CAT24C32 (SOIC), AP2112K (SOT25).
PIN_MAP = {}
for i, u in enumerate(("U3", "U4", "U5", "U6")):
    PIN_MAP.update({(u, "VIN"): [(u, "5"), (u, "8")], (u, "GND"): [(u, "1"), (u, "14")],
                    (u, "SCK"): [(u, "10")], (u, "SDI"): [(u, "12")], (u, "SDO"): [(u, "11")],
                    (u, "CS"): [(u, "9")]})
PIN_MAP.update({
    ("U1", "VIN"): [("U16", "1"), ("U16", "3"), ("R14", "1")],
    ("U1", "GND"): [("U16", "2"), ("U15", "1"), ("U1", "18"), ("U1", "20"), ("U1", "11")],
    ("U1", "SDA"): [("U15", "5")], ("U1", "SCL"): [("U15", "6")],
    ("U2", "VIN"): [("U2", "2"), ("U2", "5"), ("U2", "6"), ("U2", "8")],
    ("U2", "GND"): [("U2", "1"), ("U2", "7")],
    ("U2", "SDA"): [("U2", "3")], ("U2", "SCL"): [("U2", "4")],
    ("U7", "VDD"): [("U7", "2")], ("U7", "GND"): [("U7", "1")],
    ("U7", "SDA"): [("U7", "3")], ("U7", "SCL"): [("U7", "4")],
    ("U8", "VDD"): [("U8", "8")], ("U8", "GND"): [("U8", "3")], ("U8", "ADDR"): [("U8", "1")],
    ("U8", "SDA"): [("U8", "9")], ("U8", "SCL"): [("U8", "10")],
    ("U8", "A0"): [("R20", "1")], ("U8", "A1"): [("R21", "1")],
    ("U8", "A2"): [("R22", "1")], ("U8", "A3"): [("R23", "1")],
    ("U13", "VCC"): [("U13", "8")], ("U13", "VSS"): [("U13", "4")], ("U13", "A0"): [("U13", "1")],
    ("U13", "A1"): [("U13", "2")], ("U13", "A2"): [("U13", "3")], ("U13", "SDA"): [("U13", "5")],
    ("U13", "SCL"): [("U13", "6")], ("U13", "WP"): [("U13", "7")],
    ("U14", "LV"): [("U14", "2")], ("U14", "HV"): [("R19", "1")], ("U14", "GND"): [("U14", "1")],
    ("U14", "LSDA"): [("U14", "4")], ("U14", "LSCL"): [("U14", "3")],
    ("U14", "HSDA"): [("U14", "5")], ("U14", "HSCL"): [("U14", "6")],
})

# Rev A support circuitry the DIY modules carry on board; not in netlist.csv.
EXTRA = {
    "1V8": [("U16", "5"), ("U1", "8"), ("U1", "13"), ("U1", "9"), ("U1", "22"), ("U15", "2"),
            ("R15", "1"), ("R16", "1"), ("C16", "1"), ("C17", "1"), ("C20", "1")],
    "I2C1_SDA_1V8": [("U1", "24"), ("U15", "4"), ("R15", "2")],
    "I2C1_SCL_1V8": [("U1", "23"), ("U15", "3"), ("R16", "2")],
    "IMU_REGOUT": [("U1", "10"), ("C18", "1")],
    "I2C1_EN": [("U15", "7"), ("U15", "8"), ("R14", "2"), ("C21", "1")],
    "I2C0_EN": [("U14", "7"), ("U14", "8"), ("R19", "2"), ("C25", "1")],
    "5V": [("R17", "1"), ("R18", "1"), ("C23", "1")],
    "I2C0_SDA_5V": [("R17", "2")],
    "I2C0_SCL_5V": [("R18", "2")],
    "3V3": [("C19", "1"), ("C22", "1"), ("C24", "1")]
           + [(f"C{4 + 3 * i}", "1") for i in range(4)] + [(f"C{5 + 3 * i}", "1") for i in range(4)],
    "GND": [("C16", "2"), ("C17", "2"), ("C18", "2"), ("C19", "2"), ("C20", "2"), ("C21", "2"),
            ("C22", "2"), ("C23", "2"), ("C24", "2"), ("C25", "2")]
           + [(f"C{4 + 3 * i}", "2") for i in range(4)] + [(f"C{5 + 3 * i}", "2") for i in range(4)]
           + [(f"C{26 + i}", "2") for i in range(4)],
}
for i in range(4):
    EXTRA[f"CHT{i + 1}_TP"] = [(f"J{3 + i}", "2"), (f"U{3 + i}", "4"), (f"C{6 + 3 * i}", "1")]
    EXTRA[f"CHT{i + 1}_TN"] = [(f"J{3 + i}", "1"), (f"U{3 + i}", "3"), (f"C{6 + 3 * i}", "2")]
    EXTRA[f"ADC_A{i}_F"] = [(f"R{20 + i}", "2"), (f"C{26 + i}", "1"), ("U8", str(4 + i))]

# BME680 sits on a peninsula with no pour, so its supplies reach the planes through these vias.
NECK_VIAS = {"GND": (13.2, 30.6), "3V3": (13.2, 33.4)}
PENINSULA = (0.0, 26.6, 12.0, 37.8)


# Top silkscreen: text, x, y, size, bold, justification
TEXTS = [(f"U{3 + i}", CX[i] + 0.2, 21.8, 0.7, False, "c") for i in range(4)]
TEXTS += [(f"CHT{i + 1}", CX[i] + 4.0, 16.2, 0.75, True, "c") for i in range(4)]
TEXTS += [("+", CX[i] - 1.75, 16.3, 0.9, True, "c") for i in range(4)]     # J3-J6 pad 2 = T+
TEXTS += [("-", CX[i] + 1.95, 15.75, 0.9, True, "c") for i in range(4)]    # J3-J6 pad 1 = T-
TEXTS += [(f"A{i}", 26.0 + 3.5 * i, 43.9, 0.6, False, "c") for i in range(4)]
TEXTS += [("GND", 40.0, 46.6, 0.6, False, "c")]
# Port names: TE datasheet p.7, seen from the top with the ports pointing left, Port 2 is the upper one.
TEXTS += [("ICM-20948", 3.9, 15.4, 0.7, True, "c"), ("9-AXIS IMU", 3.9, 16.6, 0.6, False, "c"),
          ("PORT 2", 2.6, 40.5, 0.6, False, "c"), ("PORT 1", 3.4, 49.95, 0.6, False, "c"),
          ("MS4525DO", 21.3, 44.2, 0.7, True, "c"), ("AIRSPEED", 21.3, 45.4, 0.6, False, "c"),
          ("EGT RIBBON", 56.8, 50.2, 0.7, True, "c"),
          ("RB01HAT", 44.0, 52.2, 2.0, True, "l"), ("REV A CONCEPT", 44.0, 54.2, 0.7, False, "l"),
          ("RB-AVIONICS", 44.0, 55.3, 0.7, False, "l")]


# Bottom silkscreen, in the quiet area between the ADC and the ribbon header
BACK_TEXTS = [("RB01HAT", 48.5, 41.2, 2.1, True), ("Rev A concept", 48.5, 43.9, 0.8, False),
              ("not for fabrication", 48.5, 45.1, 0.8, False), ("RB-Avionics", 48.5, 46.3, 0.8, False)]


def text_box(s, x, y, size, just):
    width = len(s) * size * 0.8
    x0 = x - width / 2 if just == "c" else x
    return x0, y - size * 0.75, x0 + width, y + size * 0.75


def load_netlist():
    with open(ROOT / "hardware" / "netlist.csv", newline="") as f:
        rows = [r for r in csv.DictReader(line for line in f if not line.startswith("#"))]
    with open(ROOT / "hardware" / "parts.csv", newline="") as f:
        location = {r["ref"]: r["location"] for r in csv.DictReader(f)}
    return [r for r in rows if r["net"] != "NC" and location[r["ref"]] != "EXT"]


def resolve_nets():
    """Return {net: [(ref, pad), ...]} and check every on-board netlist row lands on a pad."""
    nets = defaultdict(list)
    rows = load_netlist()
    for r in rows:
        nets[r["net"]].extend(PIN_MAP.get((r["ref"], r["pin"]), [(r["ref"], r["pin"])]))
    for net, pads in EXTRA.items():
        nets[net].extend(pads)
    for net in nets:
        nets[net] = list(dict.fromkeys(nets[net]))
    owner = {}
    for net, pads in nets.items():
        for key in pads:
            if key in owner and owner[key] != net:
                raise SystemExit(f"pad {key} is on both {owner[key]} and {net}")
            owner[key] = net
    return nets, rows


# ------------------------------------------------------------------ library
def write_custom_footprint():
    LIB.mkdir(parents=True, exist_ok=True)
    pads = []
    for i, x in enumerate((-3.81, -1.27, 1.27, 3.81)):
        pads.append((str(1 + i), x, 6.35))          # 1-4 on the bottom row, port side first
        pads.append((str(8 - i), x, -6.35))         # 8-5 on the top row
    text = ['(footprint "MS4525DO_DS_DIP-8"', '  (version 20241229)', '  (generator "pcbnew")',
            '  (layer "F.Cu")',
            '  (descr "TE MS4525DO dual side port, pin style P. Datasheet 04/2019, pages 7 and 11. '
            'Concept footprint: confirm pad and drill against the current TE drawing.")',
            '  (attr through_hole)',
            '  (property "Reference" "REF**" (at 0 -8.2 0) (layer "F.SilkS") '
            '(effects (font (size 1 1) (thickness 0.15))))',
            '  (property "Value" "MS4525DO" (at 0 8.2 0) (layer "F.Fab") '
            '(effects (font (size 1 1) (thickness 0.15))))',
            '  (fp_poly (pts (xy -5.2 -7.25) (xy 5.2 -7.25) (xy 5.2 7.25) (xy -5.2 7.25) (xy -5.2 4) '
            '(xy -12.7 4) (xy -12.7 -4) (xy -5.2 -4)) (stroke (width 0.05) (type solid)) (fill none) '
            '(layer "F.CrtYd"))',
            '  (fp_rect (start -4.95 -5.2) (end 4.95 5.2) (stroke (width 0.1) (type solid)) '
            '(fill none) (layer "F.Fab"))']
    for num, x, y in pads:
        shape = "rect" if num == "1" else "circle"
        text.append(f'  (pad "{num}" thru_hole {shape} (at {x} {y}) (size 1.4 1.4) (drill 0.8) '
                    '(layers "*.Cu" "*.Mask"))')
    text.append('  (model "${KIPRJMOD}/3dmodels/MS4525DO-DS_DIP.wrl" (offset (xyz 0 0 0)) '
                '(scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    text.append(")")
    (LIB / "MS4525DO_DS_DIP-8.kicad_mod").write_text("\n".join(text) + "\n")


def write_ms4525_model():
    """Simple VRML model from the datasheet outline. KiCad VRML unit: 0.1 inch."""
    MODELS.mkdir(exist_ok=True)
    u = 1 / 2.54
    shapes = []

    def add(points, faces, color, spec=0.3, shine=0.3):
        shapes.append((points, faces, color, spec, shine))

    def box(x0, x1, y0, y1, z0, z1, color, **kw):
        pts = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        add(pts, [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)], color, **kw)

    def frustum(x0, x1, r0, r1, y, z, color, n=32, **kw):
        pts, faces = [], []
        for x, r in ((x0, r0), (x1, r1)):
            pts += [(x, y + r * math.cos(2 * math.pi * k / n), z + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        for k in range(n):
            a, b = k, (k + 1) % n
            faces.append((a, b, n + b, n + a))
        faces.append(tuple(range(n)))
        faces.append(tuple(range(2 * n - 1, n - 1, -1)))
        add(pts, faces, color, **kw)

    body, port, metal, hole = (0.13, 0.13, 0.14), (0.16, 0.16, 0.17), (0.72, 0.72, 0.70), (0.02, 0.02, 0.02)
    z0, z1 = 1.5, 8.7
    box(-4.95, 4.95, -5.2, 5.2, z0, z0 + 3.4, body)
    box(-4.95, 4.95, -5.2, 5.2, z0 + 3.5, z1, port, spec=0.4, shine=0.4)
    for x in (-3.81, -1.27, 1.27, 3.81):
        for s in (-1, 1):
            box(x - 0.25, x + 0.25, sorted((s * 5.2, s * 6.5))[0], sorted((s * 5.2, s * 6.5))[1], 3.0, 3.3, metal, spec=0.8, shine=0.6)
            box(x - 0.25, x + 0.25, s * 6.35 - 0.15, s * 6.35 + 0.15, -3.0, 3.3, metal, spec=0.8, shine=0.6)
    for y, z in ((2.15, z0 + 5.4), (-2.15, z0 + 1.8)):
        frustum(-4.95, -7.6, 1.15, 1.15, y, z, port, spec=0.4, shine=0.4)
        frustum(-7.6, -8.2, 1.15, 1.75, y, z, port, spec=0.4, shine=0.4)
        frustum(-8.2, -12.45, 1.75, 1.25, y, z, port, spec=0.4, shine=0.4)
        frustum(-12.46, -12.5, 0.75, 0.75, y, z, hole)
    out = ["#VRML V2.0 utf8"]
    for pts, faces, c, spec, shine in shapes:
        coords = ", ".join(f"{x * u:.4f} {y * u:.4f} {z * u:.4f}" for x, y, z in pts)
        index = ", ".join(", ".join(str(i) for i in f) + ", -1" for f in faces)
        out.append(
            "Shape { appearance Appearance { material Material { "
            f"diffuseColor {c[0]} {c[1]} {c[2]} specularColor {spec} {spec} {spec} shininess {shine} "
            "} } geometry IndexedFaceSet { creaseAngle 0.6 solid FALSE "
            f"coord Coordinate {{ point [ {coords} ] }} coordIndex [ {index} ] }} }}")
    (MODELS / "MS4525DO-DS_DIP.wrl").write_text("\n".join(out) + "\n")


# ------------------------------------------------------------------ board
def seg(board, a, b, layer=pcbnew.Edge_Cuts, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(*a))
    s.SetEnd(P(*b))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def arc(board, a, m, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(P(*a), P(*m), P(*b))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


def outline(board):
    r = 3.0
    d = r * (1 - math.sqrt(0.5))
    y1, y2, y3, y4 = 27.0, 28.0, 36.5, 37.5        # the two milled slots along the BME680 peninsula
    sx, sw = 10.6, 11.6
    pts = [(r, 0), (W - r, 0)]
    for a, b in zip(pts, pts[1:]):
        seg(board, a, b)
    arc(board, (W - r, 0), (W - d, d), (W, r))
    seg(board, (W, r), (W, H - r))
    arc(board, (W, H - r), (W - d, H - d), (W - r, H))
    seg(board, (W - r, H), (r, H))
    arc(board, (r, H), (d, H - d), (0, H - r))
    path = [(0, H - r), (0, y4), (sw, y4), (sw, 34.6), (sx, 34.6), (sx, y3), (0, y3), (0, y2),
            (sx, y2), (sx, 29.8), (sw, 29.8), (sw, y1), (0, y1), (0, r)]
    for a, b in zip(path, path[1:]):
        seg(board, a, b)
    arc(board, (0, r), (d, d), (r, 0))


def load_fp(lib, name):
    path = str(LIB) if lib == "RB01HAT" else f"{FP}/{lib}.pretty"
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib}:{name}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def place(board):
    fps = {}
    for ref, ((lib, name), value, x, y, rot) in PARTS.items():
        fp = load_fp(lib, name)
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(P(x, y))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
        fps[ref] = fp
    # The ICM-20948 die pad must not be soldered (datasheet 4.4): drop the generic EP and its paste.
    qfn = fps["U1"]
    for pad in list(qfn.Pads()):
        if pad.GetNumber() in ("", "25"):
            qfn.Remove(pad)
    for ref, (x, y) in HOLES.items():
        fp = load_fp(*HOLE)
        fp.SetReference(ref)
        fp.SetValue("M2.5")
        fp.SetPosition(P(x, y))
        fp.Reference().SetVisible(False)
        board.Add(fp)
        fps[ref] = fp
    j1 = load_fp(*SOCKET)
    j1.SetReference("J1")
    j1.SetValue("Pi 5 GPIO")
    board.Add(j1)
    j1.Flip(P(0, 0), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    j1.SetOrientationDegrees(270)
    j1.SetPosition(P(*J1_PIN1))
    fps["J1"] = j1
    pads = {p.GetNumber(): rel(p.GetPosition()) for p in j1.Pads()}
    for pin, want in (("1", (8.37, 4.77)), ("2", (8.37, 2.23)), ("39", (56.63, 4.77)), ("40", (56.63, 2.23))):
        got = pads[pin]
        if abs(got[0] - want[0]) > 0.01 or abs(got[1] - want[1]) > 0.01:
            raise SystemExit(f"J1 pin {pin} at {got}, expected {want}: header orientation is wrong")
    return fps


def assign_nets(board, fps, nets, rows):
    infos = {}
    for name in sorted(nets):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        infos[name] = ni
    terminals = defaultdict(list)
    for net, keys in sorted(nets.items()):
        for ref, num in keys:
            pads = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if not pads:
                raise SystemExit(f"{ref} has no pad {num} (net {net})")
            for pad in pads:
                pad.SetNet(infos[net])
                terminals[net].append(pad)
    for pad in fps["J1"].Pads():        # solid to the pours: the header carries the HAT's whole return current
        if pad.GetNetname() == "GND":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for r in rows:      # every on-board row of netlist.csv must sit on a pad of that net
        for ref, num in PIN_MAP.get((r["ref"], r["pin"]), [(r["ref"], r["pin"])]):
            names = {p.GetNetname() for p in fps[ref].Pads() if p.GetNumber() == num}
            if names != {r["net"]}:
                raise SystemExit(f"netlist row {r['net']} {r['ref']}.{r['pin']} -> {ref}.{num} has {names}")
    return infos, terminals


# ------------------------------------------------------------------ router
class Grid:
    """occ: legal track centres, ovia: legal via centres. 0 free, n reserved for net n, -1 blocked."""

    def __init__(self):
        self.occ = np.zeros((2, NX, NY), np.int16)
        self.ovia = np.zeros((2, NX, NY), np.int16)

    def copy(self):
        g = Grid()
        g.occ, g.ovia = self.occ.copy(), self.ovia.copy()
        return g

    @staticmethod
    def apply(arr, x0, x1, y0, y1, net, mask=None):
        sub = arr[x0:x1, y0:y1]
        m = np.ones(sub.shape, bool) if mask is None else mask
        if net <= 0:
            sub[m] = -1
        else:
            sub[m & (sub == 0)] = net
            sub[m & (sub != net)] = -1

    @staticmethod
    def window(x0, x1, y0, y1):
        return (max(0, int(math.floor(x0 / G))), min(NX, int(math.ceil(x1 / G)) + 1),
                max(0, int(math.floor(y0 / G))), min(NY, int(math.ceil(y1 / G)) + 1))

    def rect(self, arr, layer, x0, y0, x1, y1, net, d):
        # exact on purpose: rounding outward closes the escape channels of a 0.4 mm pitch QFN
        ix0, ix1 = max(0, math.ceil((x0 - d) / G - 1e-9)), min(NX, math.floor((x1 + d) / G + 1e-9) + 1)
        iy0, iy1 = max(0, math.ceil((y0 - d) / G - 1e-9)), min(NY, math.floor((y1 + d) / G + 1e-9) + 1)
        if ix0 < ix1 and iy0 < iy1:
            self.apply(arr[layer], ix0, ix1, iy0, iy1, net)

    def capsule(self, arr, layer, a, b, r, net):
        ix0, ix1, iy0, iy1 = self.window(min(a[0], b[0]) - r, max(a[0], b[0]) + r,
                                         min(a[1], b[1]) - r, max(a[1], b[1]) + r)
        if ix0 >= ix1 or iy0 >= iy1:
            return
        xs = np.arange(ix0, ix1)[:, None] * G
        ys = np.arange(iy0, iy1)[None, :] * G
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else np.clip(((xs - a[0]) * dx + (ys - a[1]) * dy) / l2, 0, 1)
        mask = (xs - (a[0] + t * dx)) ** 2 + (ys - (a[1] + t * dy)) ** 2 <= r * r
        self.apply(arr[layer], ix0, ix1, iy0, iy1, net, mask)

    def add_track(self, layer, a, b, net):
        self.capsule(self.occ, layer, a, b, TW + CL + MARGIN, net)
        self.capsule(self.ovia, layer, a, b, TW / 2 + CL + VD / 2 + MARGIN, net)

    def add_via(self, p, net):
        for layer in (0, 1):
            self.capsule(self.occ, layer, p, p, VD / 2 + CL + TW / 2 + MARGIN, net)
            self.capsule(self.ovia, layer, p, p, VD + CL + MARGIN, net)

    def add_pad(self, layer, box, net):
        x0, y0, x1, y1 = box
        self.rect(self.occ, layer, x0, y0, x1, y1, net, CL + TW / 2 + MARGIN)
        self.rect(self.ovia, layer, x0, y0, x1, y1, net, CL + VD / 2 + MARGIN)


VIA_COST = 26.0
_lib = None


def core():
    """Compile astar.c once per run: the search runs thousands of times per routing attempt."""
    global _lib
    if _lib is None:
        out = Path(tempfile.mkdtemp(prefix="rb01hat-")) / "astar.so"
        subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", str(out), str(HERE / "astar.c"), "-lm"], check=True)
        _lib = ctypes.CDLL(str(out))
        _lib.astar.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_float, ctypes.c_long, ctypes.c_void_p, ctypes.c_int]
        _lib.astar.restype = ctypes.c_int
    return _lib


def astar(free, free_via, sources, goal, target=None, allow_via=True, limit=0):
    """Return [(layer, x, y), ...] from a source to a goal cell, or None. goal: bytes, 2 * NX * NY."""
    src = np.array(sorted(sources), dtype=np.int32)
    out = np.zeros(3 * 40000, dtype=np.int32)
    tx, ty = target if target else (-1, -1)
    n = core().astar(free[0], free[1], free_via, NX, NY, src.ctypes.data, len(src), goal, tx, ty,
                     int(allow_via), VIA_COST, limit, out.ctypes.data, 40000)
    if n <= 0:
        return None
    return [tuple(int(v) for v in out[3 * i:3 * i + 3]) for i in range(n)]


def goal_map(cells):
    g = np.zeros((2, NX, NY), np.uint8)
    for l, x, y in cells:
        g[l, x, y] = 1
    return g.tobytes()


def masks(grid, nid):
    occ, ovia = grid.occ, grid.ovia
    free = [(((occ[l] == 0) | (occ[l] == nid)).astype(np.uint8)).tobytes() for l in (0, 1)]
    v = ((ovia[0] == 0) | (ovia[0] == nid)) & ((ovia[1] == 0) | (ovia[1] == nid))
    return free, v.astype(np.uint8).tobytes()


class Terminal:
    def __init__(self, pad=None, point=None):
        if pad is not None:
            self.name = f"{pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}"
            self.center = rel(pad.GetPosition())
            box = pad.GetBoundingBox()
            a, b = rel(box.GetOrigin()), rel(box.GetEnd())
            self.box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            self.tht = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            self.npth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
            self.back = not self.tht and pad.IsOnLayer(pcbnew.B_Cu)
        else:
            self.name = f"via{point}"
            self.center = point
            self.box = (point[0] - VD / 2, point[1] - VD / 2, point[0] + VD / 2, point[1] + VD / 2)
            self.tht, self.npth, self.back = True, False, False

    @property
    def layers(self):
        return (0, 1) if self.tht else ((1,) if self.back else (0,))

    def cells(self, free):
        """Grid cells inside the pad usable by this net, nearest to the pad centre first."""
        x0, y0, x1, y1 = self.box
        cx, cy = self.center
        out = []
        for l in self.layers:
            for ix in range(int(math.ceil(x0 / G)), int(math.floor(x1 / G)) + 1):
                for iy in range(int(math.ceil(y0 / G)), int(math.floor(y1 / G)) + 1):
                    if 0 <= ix < NX and 0 <= iy < NY and free[l][ix * NY + iy]:
                        out.append(((ix * G - cx) ** 2 + (iy * G - cy) ** 2, l, ix, iy))
        out.sort()
        limit = out[0][0] + 0.09 if out else 0
        return [(l, x, y) for dist, l, x, y in out if dist <= limit][:40]


def emit(path, nid, tracks, vias, grid):
    """Turn a cell path into merged segments and vias, and reserve them on the grid."""
    i = 0
    while i < len(path) - 1:
        l, x, y = path[i]
        nl, nx, ny = path[i + 1]
        if nl != l:
            p = (x * G, y * G)
            vias.append((nid, p))
            grid.add_via(p, nid)
            i += 1
            continue
        dx, dy = nx - x, ny - y
        j = i + 1
        while j + 1 < len(path):
            ll, xx, yy = path[j + 1]
            if ll != l or xx - path[j][1] != dx or yy - path[j][2] != dy:
                break
            j += 1
        a = (x * G, y * G)
        b = (path[j][1] * G, path[j][2] * G)
        tracks.append((nid, l, a, b))
        grid.add_track(l, a, b, nid)
        i = j


def stub(tracks, grid, nid, l, cell, center):
    p = (cell[0] * G, cell[1] * G)
    if math.hypot(p[0] - center[0], p[1] - center[1]) > 1e-6:
        tracks.append((nid, l, p, center))
        grid.add_track(l, p, center, nid)


def base_grid(board, terminals, ids):
    grid = Grid()
    # board edge and slots
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            a, b = rel(d.GetStart()), rel(d.GetEnd())
            for l in (0, 1):
                grid.capsule(grid.occ, l, a, b, EDGE + TW / 2 + MARGIN, -1)
                grid.capsule(grid.ovia, l, a, b, EDGE + VD / 2 + MARGIN, -1)
    # corners: arcs are not straight, keep the whole corner square out
    for cx, cy in ((0, 0), (W, 0), (0, H), (W, H)):
        for l in (0, 1):
            grid.capsule(grid.occ, l, (cx, cy), (cx, cy), 3.0, -1)
            grid.capsule(grid.ovia, l, (cx, cy), (cx, cy), 3.2, -1)
    net_of = {}
    for net, pads in terminals.items():
        for pad in pads:
            net_of[(pad.GetParentFootprint().GetReference(), pad.GetNumber())] = ids[net]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            t = Terminal(pad)
            nid = net_of.get((fp.GetReference(), pad.GetNumber()), -1)
            for l in (0, 1) if (t.tht or t.npth) else t.layers:
                grid.add_pad(l, t.box, nid)
    for x, y in HOLES.values():
        for l in (0, 1):
            grid.capsule(grid.occ, l, (x, y), (x, y), 2.5, -1)
            grid.capsule(grid.ovia, l, (x, y), (x, y), 2.75, -1)
    silk_items = TEXTS + [(s_, x, y, size, bold, "c") for s_, x, y, size, bold in BACK_TEXTS]
    for s_, x, y, size, _, just in silk_items:   # vias open the solder mask and would clip the silkscreen
        x0, y0, x1, y1 = text_box(s_, x, y, size, just)
        for l in (0, 1):
            grid.rect(grid.ovia, l, x0, y0, x1, y1, -1, 0.3)
    # TDK layout guide: nothing under the IMU. Keep what the pads have already reserved.
    x, y = PARTS["U1"][2:4]
    ix0, ix1, iy0, iy1 = Grid.window(x - 2.0, x + 2.0, y - 2.0, y + 2.0)
    for arr in (grid.occ, grid.ovia):
        for l in (0, 1):
            sub = arr[l, ix0:ix1, iy0:iy1]
            sub[sub == 0] = -1
    return grid


def route(board, terminals, ids, order, grid0):
    grid = grid0.copy()
    names = {v: k for k, v in ids.items()}
    tracks, vias, failed = [], [], []

    # plane nets: each SMD pad gets a short stub to its own via, or to a neighbour's
    plane_vias = defaultdict(set)
    for net, (x, y) in NECK_VIAS.items():
        p = (round(x / G) * G, round(y / G) * G)
        vias.append((ids[net], p))
        grid.add_via(p, ids[net])
        plane_vias[net].add((int(round(x / G)), int(round(y / G))))
    groups = {}
    for net in PLANE_NETS:
        terms = [Terminal(p) for p in terminals[net] if not (p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)]
        px, py = PARTS["U1"][2:4]
        terms.sort(key=lambda t: (math.hypot(t.center[0] - px, t.center[1] - py) > 4, t.center))
        groups[net] = terms
    peninsula = {"GND": [], "3V3": []}
    for net in sorted(PLANE_NETS):
        for t in groups[net]:
            nid = ids[net]
            if t.center[0] < PENINSULA[2] and PENINSULA[1] < t.center[1] < PENINSULA[3]:
                peninsula[net].append(t)
                continue
            free, fv = masks(grid, nid)
            anchors = t.cells(free)
            if not anchors:
                failed.append(f"{net}:{t.name}")
                continue
            gap = VD / 2 + 0.12
            box = t.box
            if t.name.startswith("U1."):       # a via next to the QFN would close the neighbour's escape
                ux, uy = PARTS["U1"][2:4]
                box, gap = (ux - 2.8, uy - 2.8, ux + 2.8, uy + 2.8), 0.0
            ix0, ix1, iy0, iy1 = Grid.window(box[0] - gap, box[2] + gap, box[1] - gap, box[3] + gap)
            top = np.frombuffer(fv, np.uint8).reshape(NX, NY).copy()
            top[ix0:ix1, iy0:iy1] = 0
            for x, y in plane_vias[net]:       # join a close via instead of stacking a second one on it
                wx0, wx1, wy0, wy1 = max(0, x - 8), min(NX, x + 9), max(0, y - 8), min(NY, y + 9)
                top[wx0:wx1, wy0:wy1] = 0
            for x, y in plane_vias[net]:
                top[x, y] = 1
            goal = np.concatenate([top[None], np.zeros((1, NX, NY), np.uint8)]).tobytes()
            path = astar(free, fv, anchors, goal, allow_via=False, limit=60000)
            if path is None:
                failed.append(f"{net}:{t.name}")
                continue
            l, x, y = path[0]
            stub(tracks, grid, nid, l, (x, y), t.center)
            emit(path, nid, tracks, vias, grid)
            l, x, y = path[-1]
            if (x, y) not in plane_vias[net]:
                p = (x * G, y * G)
                vias.append((nid, p))
                grid.add_via(p, nid)
                plane_vias[net].add((x, y))

    jobs = [(n, [Terminal(p) for p in terminals[n]]) for n in order]
    for net, terms in peninsula.items():
        if terms:
            jobs.insert(0, (net, [Terminal(point=NECK_VIAS[net])] + terms))
    for net, terms in jobs:
        nid = ids[net]
        free, fv = masks(grid, nid)
        todo = list(terms)
        done = [todo.pop(0)]
        tree = set()
        anchors = {}
        for cell in done[0].cells(free):
            tree.add(cell)
            anchors[cell] = done[0].center
            if done[0].tht:
                tree.add((1 - cell[0], cell[1], cell[2]))
                anchors[(1 - cell[0], cell[1], cell[2])] = done[0].center
        while todo:
            todo.sort(key=lambda t: min(math.hypot(t.center[0] - d.center[0], t.center[1] - d.center[1]) for d in done))
            t = todo.pop(0)
            cells = t.cells(free)
            if not cells:
                failed.append(net)
                break
            targets = set(cells)
            tx, ty = int(t.center[0] / G), int(t.center[1] / G)
            path = astar(free, fv, tree, goal_map(targets), (tx, ty), limit=2500000)
            if path is None:
                failed.append(net)
                break
            first, last = path[0], path[-1]
            if first in anchors:
                stub(tracks, grid, nid, first[0], first[1:], anchors[first])
            emit(path, nid, tracks, vias, grid)
            stub(tracks, grid, nid, last[0], last[1:], t.center)
            free, fv = masks(grid, nid)
            tree.update(path)
            for l, x, y in path:
                if any(p[0] == x and p[1] == y and p[2] != l for p in path):
                    tree.add((1 - l, x, y))
            done.append(t)
            for cell in cells:
                tree.add(cell)
                anchors[cell] = t.center
                if t.tht:
                    tree.add((1 - cell[0], cell[1], cell[2]))
                    anchors[(1 - cell[0], cell[1], cell[2])] = t.center
    return tracks, vias, failed, grid


def stitch(grid, nid, vias, pitch=3.0):
    """GND vias on a regular lattice wherever nothing else is: ties the F.Cu and B.Cu pours to In1."""
    n = 0
    y = 1.5
    while y < H:
        x = 1.5
        while x < W:
            ix, iy = int(round(x / G)), int(round(y / G))
            inside = PENINSULA[0] <= x <= PENINSULA[2] and PENINSULA[1] <= y <= PENINSULA[3]
            if not inside and grid.ovia[0, ix, iy] == 0 and grid.ovia[1, ix, iy] == 0:
                p = (ix * G, iy * G)
                vias.append((nid, p))
                grid.add_via(p, nid)
                n += 1
            x += pitch
        y += pitch
    print(f"  {n} GND stitching vias")


def route_with_retries(board, terminals, ids, passes=400, budget=240):
    routed = [n for n in terminals if n not in PLANE_NETS]

    def span(net):
        pts = [rel(p.GetPosition()) for p in terminals[net]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    rng = random.Random(1)
    order = sorted(routed, key=span)
    grid0 = base_grid(board, terminals, ids)
    best = None
    t0 = time.time()
    for attempt in range(1, passes + 1):
        tracks, vias, failed, grid = route(board, terminals, ids, order, grid0)
        if best is None or len(failed) < len(best[2]):
            best = (tracks, vias, failed, grid)
            print(f"  pass {attempt}: {len(tracks)} segments, {len(vias)} vias, "
                  f"failed {failed} ({time.time() - t0:.0f} s)", flush=True)
        if not failed or time.time() - t0 > budget:
            break
        fails = [f for f in sorted({f.split(":")[0] for f in failed}) if f in order]
        rng.shuffle(fails)
        rest = [n for n in order if n not in fails]
        if attempt % 7 == 0:        # shake the order now and then to leave a local optimum
            rng.shuffle(rest)
        order = fails + rest
    return best


def add_copper(board, infos, ids, tracks, vias):
    names = {v: k for k, v in ids.items()}
    for nid, layer, a, b in tracks:
        if math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(*a))
        t.SetEnd(P(*b))
        t.SetWidth(mm(TW))
        t.SetLayer(pcbnew.F_Cu if layer == 0 else pcbnew.B_Cu)
        t.SetNet(infos[names[nid]])
        board.Add(t)
    seen = set()
    for nid, p in vias:
        key = (nid, round(p[0], 3), round(p[1], 3))
        if key in seen:
            continue
        seen.add(key)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(*p))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(mm(VD))
        v.SetDrill(mm(VDRL))
        v.SetNet(infos[names[nid]])
        board.Add(v)


def add_zones(board, infos):
    def poly(z, pts):
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(mm(OX + x), mm(OY + y))

    rect = [(0, 0), (W, 0), (W, H), (0, H)]
    for layer, net in ((pcbnew.F_Cu, "GND"), (pcbnew.In1_Cu, "GND"), (pcbnew.In2_Cu, "3V3"), (pcbnew.B_Cu, "GND")):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(infos[net])
        poly(z, rect)
        z.SetLocalClearance(mm(0.2))
        z.SetMinThickness(mm(0.2))
        z.SetThermalReliefGap(mm(0.25))
        z.SetThermalReliefSpokeWidth(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
    # Doc 06: no copper pour near the BME680
    x0, y0, x1, y1 = PENINSULA
    keep = pcbnew.ZONE(board)
    layers = pcbnew.LSET()
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        layers.AddLayer(layer)
    keep.SetLayerSet(layers)
    keep.SetIsRuleArea(True)
    keep.SetDoNotAllowZoneFills(True) if hasattr(keep, "SetDoNotAllowZoneFills") else keep.SetDoNotAllowCopperPour(True)
    keep.SetDoNotAllowTracks(False)
    keep.SetDoNotAllowVias(False)
    keep.SetDoNotAllowPads(False)
    keep.SetDoNotAllowFootprints(False)
    poly(keep, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    board.Add(keep)
    for hx, hy in HOLES.values():           # copper stays out from under the M2.5 screw heads
        ring = pcbnew.ZONE(board)
        ring.SetLayerSet(layers)
        ring.SetIsRuleArea(True)
        ring.SetDoNotAllowZoneFills(True) if hasattr(ring, "SetDoNotAllowZoneFills") else ring.SetDoNotAllowCopperPour(True)
        ring.SetDoNotAllowTracks(False)
        ring.SetDoNotAllowVias(False)
        ring.SetDoNotAllowPads(False)
        ring.SetDoNotAllowFootprints(False)
        poly(ring, [(hx + 2.4 * math.cos(math.radians(a)), hy + 2.4 * math.sin(math.radians(a))) for a in range(0, 360, 15)])
        board.Add(ring)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def silk(board, fps):
    def text(s, x, y, size=0.8, layer=pcbnew.F_SilkS, mirror=False, angle=0, just="c", bold=False):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(P(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(size * (0.2 if bold else 0.14)))
        t.SetHorizJustify({"c": pcbnew.GR_TEXT_H_ALIGN_CENTER, "l": pcbnew.GR_TEXT_H_ALIGN_LEFT,
                           "r": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[just])
        t.SetMirrored(mirror)
        t.SetTextAngleDegrees(angle)
        board.Add(t)

    labels = {"U1": (9.0, 9.2), "U2": (4.6, 29.2), "U7": None, "U8": (30.6, 43.0), "U13": (17.6, 24.9),
              "U14": (38.0, 41.8), "U15": (16.8, 14.5), "U16": (7.8, 21.6), "J1": (5.4, 7.2), "J2": None,
              "J11": None, "J3": None, "J4": None, "J5": None, "J6": None, "U3": None, "U4": None, "U5": None,
              "U6": None, "TP1": None}
    for ref, fp in fps.items():
        rt = fp.Reference()
        pos = labels.get(ref, None)
        if pos is None:
            rt.SetVisible(False)
        else:
            rt.SetVisible(True)
            rt.SetTextSize(pcbnew.VECTOR2I(mm(0.7), mm(0.7)))
            rt.SetTextThickness(mm(0.1))
            rt.SetPosition(P(*pos))
            rt.SetTextAngleDegrees(0)
            rt.SetMirrored(False)
            rt.SetLayer(pcbnew.F_SilkS)
        fp.Value().SetVisible(False)
    for item in TEXTS:
        text(*item[:4], bold=item[4], just=item[5])
    for s_, x, y, size, bold in BACK_TEXTS:
        text(s_, x, y, size=size, layer=pcbnew.B_SilkS, mirror=True, bold=bold)


STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (color "%(mask)s") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (color "%(mask)s") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
"""


def finish_files(mask=MASK):
    text = PCB.read_text()
    text = text.replace("(setup\n", "(setup\n" + STACKUP % {"mask": mask}, 1)
    text = re.sub(r'"\$\{KICAD\d?_?3DMODEL_DIR\}/[^"/]+\.3dshapes/([^"]+)"', r'"${KIPRJMOD}/3dmodels/\1"', text)
    PCB.write_text(text)
    data = json.load(open("/usr/share/kicad/template/RaspberryPi-HAT/RaspberryPi-HAT.kicad_pro"))
    data["meta"]["filename"] = PRO.name
    rules = data["board"]["design_settings"]["rules"]
    rules.update({"min_clearance": CL, "min_track_width": 0.15, "min_via_diameter": VD, "min_through_hole_diameter": VDRL,
                  "min_via_annular_width": 0.13, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.15,
                  "min_silk_clearance": 0.0, "min_text_height": 0.5})
    dflt = data["net_settings"]["classes"][0]
    dflt.update({"clearance": CL, "track_width": TW, "via_diameter": VD, "via_drill": VDRL})
    sev = data["board"]["design_settings"]["rule_severities"]
    sev.update({"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore"})
    json.dump(data, open(PRO, "w"), indent=2)
    (HERE / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n  (lib (name "RB01HAT") (type "KiCad") (uri "${KIPRJMOD}/lib/RB01HAT.pretty") '
        '(options "") (descr "RB01HAT concept footprints"))\n)\n')


def fetch_models():
    MODELS.mkdir(exist_ok=True)
    text = PCB.read_text()
    wanted = set(re.findall(r'\$\{KIPRJMOD\}/3dmodels/([^"]+\.step)"', text))
    for lib, name in [v[0] for v in PARTS.values()] + [SOCKET]:
        if lib == "RB01HAT":
            continue
        for m in re.findall(r'model "\$\{KICAD\d_3DMODEL_DIR\}/([^"]+)"', open(f"{FP}/{lib}.pretty/{name}.kicad_mod").read()):
            base = m.split("/")[-1]
            if base in wanted and not (MODELS / base).exists():
                url = MODEL_URL + "/" + urllib.parse.quote(MODEL_STANDIN.get(base, m))
                subprocess.run(["curl", "-sS", "-f", "-m", "90", "-L", "-o", str(MODELS / base), url], check=True)
                print("  fetched", base, (MODELS / base).stat().st_size)


def drc():
    out = Path(tempfile.mkdtemp(prefix="rb01hat-")) / "drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", str(out), str(PCB)],
                   check=True, capture_output=True)
    report = json.load(open(out))
    counts = defaultdict(int)
    details = []
    for v in report.get("violations", []):
        counts[(v["severity"], v["type"])] += 1
        details.append(v)
    unconnected = report.get("unconnected_items", [])
    for u in unconnected:
        counts[(u.get("severity", "error"), "unconnected")] += 1
    for k, n in sorted(counts.items()):
        print(f"  {k[0]:8s}{k[1]:32s}{n}")
    errors = sum(n for k, n in counts.items() if k[0] == "error")
    print(f"  DRC: {errors} error(s), {len(details) + len(unconnected) - errors} warning(s)")
    for v in details + unconnected:
        where = "; ".join(f"{i['description'][:50]} @({i['pos']['x'] - OX:.2f}, {i['pos']['y'] - OY:.2f})" for i in v["items"])
        print(f"    {v.get('type', 'unconnected')}: {where}")
    return report, errors


ANGLED = ["--light-top", "0.55", "--light-bottom", "0.45", "--light-side", "0.22", "--light-camera", "0.35"]
# Straight-down views: any light on the vertical axis mirrors off the mask and washes the red out to
# pink, so these use the raking side lights only, with cast shadows off (see no_shadow_config).
FLAT = ["--light-top", "0", "--light-bottom", "0", "--light-side", "0.55", "--light-camera", "0.03",
        "--light-side-elevation", "55"]
VIEWS = {
    "hero": dict(rotate="-50,0,-22", zoom="0.86", perspective=True, lights=ANGLED),
    "right": dict(rotate="-50,0,24", zoom="0.86", perspective=True, lights=ANGLED),
    "top": dict(side="top", zoom="1.12", lights=FLAT),
    "bottom": dict(side="bottom", zoom="1.12", lights=FLAT),
}


def clean_alpha(fg):
    """Drop the half-transparent shadow ghosts the raytracer leaves on a transparent background."""
    from PIL import ImageFilter
    alpha = fg.getchannel("A").point(lambda v: 255 if v >= 240 else 0)
    fg.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.7)))
    return fg


def no_shadow_config():
    """A throwaway KiCad config with cast shadows off: seen straight down they fall as hard diamonds.

    kicad-cli has no switch for this, only a config file. KICAD_CONFIG_HOME keeps it away from the
    user's own settings.
    """
    home = Path(tempfile.mkdtemp(prefix="rb01hat-kicad-"))
    (home / "9.0").mkdir()
    (home / "9.0" / "3d_viewer.json").write_text(json.dumps({"render": {
        "raytrace_shadows": False, "raytrace_post_processing": True, "raytrace_anti_aliasing": True,
        "raytrace_procedural_textures": True, "raytrace_reflections": True, "raytrace_refractions": True,
        "raytrace_backfloor": False}}))
    return dict(os.environ, KICAD_CONFIG_HOME=str(home))


def studio(png, out, size):
    """Lay a transparent render on a dark gradient, with a soft shadow, and save it as JPG."""
    from PIL import Image, ImageFilter
    fg = clean_alpha(Image.open(png).convert("RGBA"))
    fg = fg.crop(fg.getbbox())
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w]
    r = np.clip(np.hypot((xs - w / 2) / (0.75 * w), (ys - h * 0.46) / (0.75 * h)), 0, 1)[..., None]
    grad = np.array((58, 61, 68)) * (1 - r) + np.array((16, 17, 20)) * r
    canvas = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
    at = ((w - fg.width) // 2, (h - fg.height) // 2)
    k = h / 2160
    for blur, drop, strength in ((70, 70, 0.55), (18, 16, 0.45)):
        alpha = Image.new("L", size, 0)
        alpha.paste(fg.getchannel("A"), (at[0], at[1] + int(drop * k)))
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur * k)).point(lambda v: int(v * strength))
        canvas.paste((0, 0, 0, 255), (0, 0), alpha)
    canvas.alpha_composite(fg, at)
    canvas.convert("RGB").save(out, quality=95, subsampling=0, optimize=True)


def render(width=3840, height=2160):
    RENDERS.mkdir(exist_ok=True)
    flat_env = no_shadow_config()
    for name, v in VIEWS.items():
        png = RENDERS / f".{name}.png"
        flat = v["lights"] is FLAT
        cmd = ["kicad-cli", "pcb", "render", "-o", str(png), "-w", str(width), "-h", str(height),
               "--quality", "user" if flat else "high",
               "--background", "transparent", "--zoom", v["zoom"]] + v["lights"]
        if v.get("side"):
            cmd += ["--side", v["side"]]
        if v.get("rotate"):
            cmd += ["--rotate", v["rotate"]]
        if v.get("perspective"):
            cmd.append("--perspective")
        subprocess.run(cmd + [str(PCB)], check=True, capture_output=True, timeout=2400,
                       env=flat_env if flat else None)
        out = RENDERS / f"{NAME}-{name}.jpg"
        studio(png, out, (width, height))
        png.unlink()
        print(f"  {out.name} {out.stat().st_size // 1024} KiB")


def main():
    write_custom_footprint()
    write_ms4525_model()
    nets, rows = resolve_nets()
    board = pcbnew.NewBoard(str(PCB))
    board.SetCopperLayerCount(4)
    board.SetEnabledLayers(board.GetEnabledLayers())
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(4)
    outline(board)
    fps = place(board)
    infos, terminals = assign_nets(board, fps, nets, rows)
    ids = {n: i + 1 for i, n in enumerate(sorted(terminals))}
    print(f"{len(fps)} footprints, {len(nets)} nets, {len(rows)} netlist rows checked against pads")
    tracks, vias, failed, grid = route_with_retries(board, terminals, ids)
    stitch(grid, ids["GND"], vias)
    add_copper(board, infos, ids, tracks, vias)
    add_zones(board, infos)
    silk(board, fps)
    tb = board.GetTitleBlock()
    tb.SetTitle("RB01HAT Rev A concept")
    tb.SetCompany("RB-Avionics")
    tb.SetRevision("concept")
    tb.SetComment(0, "Concept from hardware/netlist.csv and docs/06-custom-pcb.md: not for fabrication")
    tb.SetComment(1, "Generated by generate.py: change the script, not this file")
    pcbnew.SaveBoard(str(PCB), board)
    finish_files()
    fetch_models()
    report, errors = drc()
    if failed:
        print("UNROUTED:", failed)
    if "--preview" in sys.argv:
        render(1600, 900)
    elif "--render" in sys.argv:
        render()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

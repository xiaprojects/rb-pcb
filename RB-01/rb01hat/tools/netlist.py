#!/usr/bin/env python3
"""Validate the RB01HAT hardware data and generate the derived docs.

Sources of truth (hardware/):
  pi5-header.csv     40-pin header reference (physical pin -> BCM GPIO)
  gpio-reserved.csv  GPIOs that are reserved or kept spare
  parts.csv          every reference designator
  netlist.csv        every connection, one row per node, daisy-chain order
  bom-diy.csv        purchasing list for the DIY build

Usage:
  python3 tools/netlist.py check         # validate; exit 1 on errors
  python3 tools/netlist.py gen           # validate, then rewrite docs/generated/*.md
  python3 tools/netlist.py rbems [DIR]   # cross-check against the rb-ems-go JSON configs
                                         # (DIR default: $RB_EMS_GO or ../../rb-ems-go)

Standard library only: this module is also imported by software/bringup on the Pi.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / "hardware"
GEN = ROOT / "docs" / "generated"

HOST = "J1"                      # refdes of the Pi header on the HAT
POWER_NETS = {"3V3", "5V", "GND"}
NC_NET = "NC"
SUPPLY_PINS = ("VIN", "VDD", "VCC")
RIBBON = ("J11", "J12")          # HAT <-> extension harness, pin n <-> pin n


@dataclass(frozen=True)
class HeaderPin:
    pin: int
    name: str
    bcm: int | None
    type: str
    functions: str


@dataclass(frozen=True)
class Reservation:
    bcm: int
    status: str
    allowed_nets: frozenset[str]
    reason: str


@dataclass(frozen=True)
class Part:
    ref: str
    kind: str
    priority: int
    function: str
    part: str
    bus: str
    i2c_addr: int | None
    supply: str
    location: str
    dnp: bool
    notes: str


@dataclass(frozen=True)
class Node:
    net: str
    ref: str
    pin: str
    note: str
    line: int


@dataclass
class Project:
    header: dict[int, HeaderPin]
    reserved: dict[int, Reservation]
    parts: dict[str, Part]
    nodes: list[Node]
    bom_refs: set[str]
    nets: dict[str, list[Node]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for n in self.nodes:
            self.nets.setdefault(n.net, []).append(n)

    def net_of(self, ref: str, pin: str) -> str | None:
        for n in self.nodes:
            if n.ref == ref and n.pin == pin:
                return n.net
        return None

    def host_pin(self, net: str | None) -> HeaderPin | None:
        """Header pin of a signal net (first one for power nets)."""
        for n in self.nets.get(net or "", []):
            if n.ref == HOST and n.pin.isdigit():
                return self.header.get(int(n.pin))
        return None

    def gpio_of(self, ref: str, pin: str) -> int | None:
        hp = self.host_pin(self.net_of(ref, pin))
        return hp.bcm if hp else None

    def fitted(self, ref: str) -> bool:
        return ref in self.parts and not self.parts[ref].dnp

    def priority(self, ref: str) -> int:
        return self.parts[ref].priority if ref in self.parts else 0


# ----------------------------------------------------------------------------- loading

def _rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    """CSV rows with their 1-based file line numbers; '#' lines are comments."""
    with path.open(newline="", encoding="utf-8") as f:
        numbered = [(i, ln) for i, ln in enumerate(f, 1)
                    if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(ln for _, ln in numbered)
    return [(numbered[k + 1][0], {key: (val or "").strip() for key, val in row.items()})
            for k, row in enumerate(reader)]


def ref_key(ref: str) -> tuple[str, int]:
    """Natural sort key: U9 < U10, TP1 sorts under 'TP'."""
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def expand_refs(spec: str) -> list[str]:
    """'U3-U6;J11' -> ['U3', 'U4', 'U5', 'U6', 'J11']"""
    out: list[str] = []
    for tok in filter(None, (t.strip() for t in spec.split(";"))):
        m = re.fullmatch(r"([A-Z]+)(\d+)-(?:\1)?(\d+)", tok)
        if m:
            out += [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            out.append(tok)
    return out


def load(hw: Path = HW) -> Project:
    header = {}
    for _, r in _rows(hw / "pi5-header.csv"):
        header[int(r["pin"])] = HeaderPin(int(r["pin"]), r["name"],
                                          int(r["bcm"]) if r["bcm"] else None,
                                          r["type"], r["functions"])
    reserved = {}
    for _, r in _rows(hw / "gpio-reserved.csv"):
        reserved[int(r["bcm"])] = Reservation(int(r["bcm"]), r["status"],
                                              frozenset(filter(None, r["allowed_nets"].split(";"))),
                                              r["reason"])
    parts = {}
    for _, r in _rows(hw / "parts.csv"):
        parts[r["ref"]] = Part(r["ref"], r["kind"], int(r["priority"] or 0), r["function"],
                               r["part"], r["bus"],
                               int(r["i2c_addr"], 16) if r["i2c_addr"] else None,
                               r["supply"], r["location"], r["dnp"].lower() == "yes", r["notes"])
    nodes = [Node(r["net"], r["ref"], r["pin"], r["note"], line)
             for line, r in _rows(hw / "netlist.csv")]
    bom_refs: set[str] = set()
    for _, r in _rows(hw / "bom-diy.csv"):
        bom_refs.update(expand_refs(r["refs"]))
    return Project(header, reserved, parts, nodes, bom_refs)


# ----------------------------------------------------------------------------- checks

def check(p: Project) -> tuple[list[str], list[str]]:
    err: list[str] = []
    warn: list[str] = []

    seen: dict[tuple[str, str], Node] = {}
    for n in p.nodes:
        where = f"netlist.csv:{n.line}"
        if n.ref not in p.parts:
            err.append(f"{where}: unknown ref {n.ref} (add it to parts.csv)")
        if (n.ref, n.pin) in seen:
            first = seen[(n.ref, n.pin)]
            err.append(f"{where}: {n.ref}.{n.pin} already in net {first.net} (line {first.line})")
        seen.setdefault((n.ref, n.pin), n)
        if n.ref != HOST:
            continue
        if not n.pin.isdigit() or int(n.pin) not in p.header:
            err.append(f"{where}: J1 pin '{n.pin}' is not 1..40")
            continue
        hp = p.header[int(n.pin)]
        if hp.type == "power" and n.net != hp.name:
            err.append(f"{where}: J1.{hp.pin} is {hp.name} but sits in net {n.net}")
        elif hp.type == "ground" and n.net != "GND":
            err.append(f"{where}: J1.{hp.pin} is GND but sits in net {n.net}")
        elif hp.type == "gpio":
            if n.net in POWER_NETS:
                err.append(f"{where}: GPIO{hp.bcm} (J1.{hp.pin}) tied to power net {n.net}")
            res = p.reserved.get(hp.bcm)
            if res and n.net != NC_NET and n.net not in res.allowed_nets:
                err.append(f"{where}: GPIO{hp.bcm} (J1.{hp.pin}) is {res.status}: {res.reason}")

    for net, nodes in p.nets.items():
        if net == NC_NET:
            continue
        if len(nodes) < 2:
            err.append(f"net {net}: single node {nodes[0].ref}.{nodes[0].pin}")
        hosts = [n for n in nodes if n.ref == HOST]
        if net not in POWER_NETS and len(hosts) > 1:
            err.append(f"net {net}: uses {len(hosts)} header pins")
        fitted = [n for n in nodes if p.fitted(n.ref)]
        if net not in POWER_NETS and len(fitted) < 2 and len(nodes) >= 2:
            warn.append(f"net {net}: fewer than 2 fitted nodes (rest are DNP)")

    used = {n.ref for n in p.nodes}
    for ref, part in p.parts.items():
        if ref not in used:
            (warn if part.dnp else err).append(f"{ref}: not in netlist")
        if not part.dnp and ref not in p.bom_refs:
            err.append(f"{ref}: missing from bom-diy.csv")
        if part.supply:
            nets = {p.net_of(ref, sp) for sp in SUPPLY_PINS} - {None}
            if not nets:
                err.append(f"{ref}: no supply pin ({'/'.join(SUPPLY_PINS)}) in netlist")
            elif nets != {part.supply}:
                err.append(f"{ref}: supply pin on {sorted(nets)} but parts.csv says {part.supply}")
    for ref in sorted(p.bom_refs - set(p.parts)):
        err.append(f"bom-diy.csv: unknown ref {ref}")

    addrs: dict[tuple[str, int], list[str]] = {}
    for part in p.parts.values():
        if part.i2c_addr is not None and not part.dnp:
            addrs.setdefault((part.bus, part.i2c_addr), []).append(part.ref)
    for (bus, addr), refs in addrs.items():
        if len(refs) > 1:
            err.append(f"I2C address clash on {bus} 0x{addr:02X}: {', '.join(refs)}")

    for part in p.parts.values():
        if part.bus.startswith("I2C"):
            for sig in ("SDA", "SCL"):
                net = p.net_of(part.ref, sig) or ""
                if not net.startswith(f"{part.bus}_{sig}"):    # I2C0_SDA or I2C0_SDA_5V (translated)
                    err.append(f"{part.ref}: {sig} not on net {part.bus}_{sig}*")
        if part.bus.startswith("SPI"):
            for sig, suffix in (("SCK", "SCLK"), ("SDI", "MOSI"), ("SDO", "MISO")):
                if p.net_of(part.ref, sig) != f"{part.bus}_{suffix}":
                    err.append(f"{part.ref}: {sig} not on net {part.bus}_{suffix}")
            cs = p.net_of(part.ref, "CS")
            if cs is None:
                err.append(f"{part.ref}: CS pin not in netlist")
                continue
            if p.host_pin(cs) is None:
                err.append(f"{part.ref}: CS net {cs} has no header GPIO")
            sharers = [n.ref for n in p.nets[cs] if n.pin == "CS" and n.ref != part.ref]
            if sharers:
                err.append(f"{part.ref}: CS net {cs} shared with {', '.join(sharers)}")

    for n in p.nets.get("5V", []):
        part = p.parts.get(n.ref)
        if part and part.supply == "3V3":
            err.append(f"{n.ref}.{n.pin}: 3V3 part connected to the 5V rail")
    for part in p.parts.values():
        if part.supply != "5V":
            continue
        for n in (n for n in p.nodes if n.ref == part.ref and n.net not in POWER_NETS | {NC_NET}):
            hp = p.host_pin(n.net)
            if hp and hp.type == "gpio":
                err.append(f"{part.ref}.{n.pin}: 5 V part wired straight to GPIO{hp.bcm} - needs a level translator")

    for a, b in [RIBBON]:
        pins_a = {n.pin: n.net for n in p.nodes if n.ref == a}
        pins_b = {n.pin: n.net for n in p.nodes if n.ref == b}
        if pins_a != pins_b:
            err.append(f"{a}/{b}: ribbon pins must carry identical nets pin-for-pin")

    return err, warn


# ----------------------------------------------------------------------------- generation

BANNER = ("<!-- GENERATED by tools/netlist.py from hardware/*.csv - do not edit by hand. "
          "Run `make docs` after changing the CSVs. -->\n")


def _label(p: Project, n: Node) -> str:
    if n.ref == HOST and n.pin.isdigit():
        return f"J1.{n.pin} ({p.header[int(n.pin)].name})"
    tag = " (DNP)" if n.ref in p.parts and p.parts[n.ref].dnp else ""
    return f"{n.ref}.{n.pin}{tag}"


def _loc(p: Project, ref: str) -> str:
    return p.parts[ref].location if ref in p.parts else "?"


def _others(p: Project, net: str) -> str:
    if net in POWER_NETS:
        return f"{net} rail"
    return ", ".join(_label(p, n) for n in p.nets[net] if n.ref != HOST)


def gen_gpio_map(p: Project) -> str:
    net_by_pin = {int(n.pin): n.net for n in p.nodes if n.ref == HOST and n.pin.isdigit()}
    out = [BANNER, "# GPIO map - Raspberry Pi 5 40-pin header\n",
           "Physical pin numbers are the header positions (pin 1 = square pad, notch end). "
           "BCM = GPIO number used by software (gpiozero, libgpiod, device tree).\n",
           "## Pin-by-pin\n",
           "| Pin | Name | BCM | Net | Connected to | Status / notes |",
           "|---:|---|---:|---|---|---|"]
    for pin in range(1, 41):
        hp = p.header[pin]
        net = net_by_pin.get(pin, "")
        res = p.reserved.get(hp.bcm) if hp.bcm is not None else None
        if net and net != NC_NET:
            status = "used"
        elif res:
            status = f"**{res.status}** - {res.reason}"
        elif hp.type == "gpio":
            status = "free"
        elif hp.name == "5V" and "5V" not in p.nets:
            status = "not used - nothing on this HAT runs from 5 V"
        else:
            status = "not wired on HAT (same rail as the wired pins)"
        if hp.functions:
            status += f" <br><sub>{hp.functions}</sub>"
        out.append(f"| {pin} | {hp.name} | {'' if hp.bcm is None else hp.bcm} | {net} | "
                   f"{_others(p, net) if net and net != NC_NET else ''} | {status} |")

    out += ["\n## Header view (top of HAT, GPIO edge at the top, USB/Ethernet to the right)\n",
            "Odd pins are the row nearer the board centre on the Pi; even pins are the row on the board edge.\n",
            "| Net | Name | Pin | Pin | Name | Net |", "|---|---|---:|:---|---|---|"]
    for odd in range(1, 41, 2):
        a, b = p.header[odd], p.header[odd + 1]
        out.append(f"| {net_by_pin.get(odd, '')} | {a.name} | {odd} | {odd + 1} | {b.name} | "
                   f"{net_by_pin.get(odd + 1, '')} |")

    out += ["\n## Signals by GPIO (allocation vs. priority)\n",
            "| BCM | Pin | Net | Nodes | Highest-priority user |", "|---:|---:|---|---|---|"]
    rows = []
    for pin, net in net_by_pin.items():
        hp = p.header[pin]
        if hp.type != "gpio" or net == NC_NET:
            continue
        refs = [n.ref for n in p.nets[net] if n.ref != HOST and n.ref not in RIBBON]
        users = [r for r in refs if p.parts[r].kind != "passive" and not p.parts[r].dnp] or refs
        best = min(users, key=p.priority, default="")
        prio = f"P{p.priority(best)} {best} ({p.parts[best].function})" if best else "-"
        rows.append((hp.bcm, f"| {hp.bcm} | {pin} | {net} | {_others(p, net)} | {prio} |"))
    out += [r for _, r in sorted(rows)]

    out += ["\n## I2C address map\n", "| Bus | Address | Ref | Function | Part | Fitted |",
            "|---|---|---|---|---|---|"]
    for part in sorted((q for q in p.parts.values() if q.i2c_addr is not None),
                       key=lambda q: (q.bus, q.i2c_addr)):
        out.append(f"| {part.bus} | 0x{part.i2c_addr:02X} | {part.ref} | {part.function} | "
                   f"{part.part} | {'no (DNP)' if part.dnp else 'yes'} |")
    out.append("\nThe ICM-20948 magnetometer (AK09916) also appears at 0x0C on I2C1 when the IMU "
               "is put in I2C bypass mode (the bring-up script does this).\n")

    out += ["## SPI chip-select map\n", "| Ref | Function | Priority | Bus | CS net | BCM | Pin | Location |",
            "|---|---|---:|---|---|---:|---:|---|"]
    for part in sorted((q for q in p.parts.values() if q.bus.startswith("SPI")),
                       key=lambda q: (q.priority, q.function)):
        cs = p.net_of(part.ref, "CS")
        hp = p.host_pin(cs)
        out.append(f"| {part.ref} | {part.function} | P{part.priority} | {part.bus} | {cs} | "
                   f"{hp.bcm if hp else '?'} | {hp.pin if hp else '?'} | {part.location} |")
    return "\n".join(out) + "\n"


def _kind(p: Project, a: Node, b: Node) -> str:
    if {a.ref, b.ref} == set(RIBBON):
        return "ribbon (IDC)"
    la, lb = _loc(p, a.ref), _loc(p, b.ref)
    if la == lb == "EXT":
        return "EXT carrier"
    if "EXT" in (la, lb):
        return "HAT <-> EXT"
    return "HAT"


def _stage_legend(p: Project) -> str:
    stages: dict[int, list[str]] = {}
    for q in sorted(p.parts.values(), key=lambda q: ref_key(q.ref)):
        if q.priority and q.kind in ("module", "ic") and not q.dnp:
            stages.setdefault(q.priority, []).append(q.ref)
    return ", ".join(f"{k} ({' '.join(v)})" for k, v in sorted(stages.items()))


def gen_wiring_list(p: Project) -> str:
    out = [BANNER, "# DIY wiring list\n",
           "How to use this list (details in `docs/04-diy-build.md`):\n",
           "- **Stage** = highest priority number among the two ends. Build and test stage by stage: "
           "stage 0 (power) first, then " + _stage_legend(p) + ".",
           "- Signal nets are **daisy chains**: wire each row from -> to, in order. Never star-wire a bus.",
           "- Power nets are **rails**: connect every listed node to the proto board rail.",
           "- Tick `[ ]` when soldered, and again in the continuity column once beeped out.",
           "- Nodes marked (DNP) are not fitted on the DIY build: skip them.\n"]
    for net, nodes in p.nets.items():
        if net == NC_NET:
            continue
        out.append(f"## {net}\n")
        notes = [f"{_label(p, n)}: {n.note}" for n in nodes if n.note]
        if net in POWER_NETS:
            out += ["Rail: connect each node to the rail.\n",
                    "| Stage | Node | Location | Soldered | Beeped |", "|---:|---|---|:-:|:-:|"]
            for n in sorted(nodes, key=lambda n: p.priority(n.ref)):
                out.append(f"| {p.priority(n.ref)} | {_label(p, n)} | {_loc(p, n.ref)} | [ ] | [ ] |")
        else:
            out += ["| # | Stage | From | To | Run | Soldered | Beeped |",
                    "|---:|---:|---|---|---|:-:|:-:|"]
            for i, (a, b) in enumerate(zip(nodes, nodes[1:]), 1):
                stage = max(p.priority(a.ref), p.priority(b.ref))
                out.append(f"| {i} | {stage} | {_label(p, a)} | {_label(p, b)} | {_kind(p, a, b)} "
                           f"| [ ] | [ ] |")
        if notes:
            out.append("\nNotes: " + "; ".join(notes))
        out.append("")
    nc = p.nets.get(NC_NET, [])
    if nc:
        out += ["## Deliberately unconnected pins\n", "| Pin | Why |", "|---|---|"]
        out += [f"| {_label(p, n)} | {n.note or 'see first row of this ref'} |" for n in nc]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------- rb-ems-go cross-check

def rbems_dir(arg: str | None = None) -> Path:
    return Path(arg or os.environ.get("RB_EMS_GO") or ROOT.parent.parent / "rb-ems-go")


def rbems(p: Project, rbdir: Path) -> tuple[list[str], list[str], list[str]]:
    """Compare the HAT with the rb-ems-go JSON configs (the pin-mapping authority)."""
    err: list[str] = []
    warn: list[str] = []
    info: list[str] = []

    def load_json(rel: str) -> dict | None:
        path = rbdir / rel
        if not path.exists():
            warn.append(f"{rel}: not found in {rbdir}")
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    hat_gpio = {p.header[int(n.pin)].bcm: n.net for n in p.nodes
                if n.ref == HOST and n.net != NC_NET and p.header[int(n.pin)].type == "gpio"}
    spi_parts = [q for q in p.parts.values() if q.bus.startswith("SPI") and not q.dnp]
    by_cs = {(q.bus, p.gpio_of(q.ref, "CS")): q for q in spi_parts}

    def off_hat(where: str, g: int) -> None:
        res = p.reserved.get(g)
        if g in hat_gpio:
            err.append(f"{where}: GPIO{g} is used on the HAT by net {hat_gpio[g]}")
        elif res and res.status in ("rb-ems", "reserved"):
            info.append(f"{where}: GPIO{g} off-HAT, reserved ({res.reason})")
        else:
            warn.append(f"{where}: GPIO{g} is not marked rb-ems in gpio-reserved.csv")

    cfg = load_json("ems-chtegt.json")
    if cfg:
        hz = cfg.get("busSpeed", 0) / 1e6               # periph physic.Frequency is in micro-hertz
        msg = f"ems-chtegt.json busSpeed = {hz / 1e6:g} MHz"
        if hz > 5e6:
            err.append(msg + " - above the MAX31856 5 MHz limit")
        elif hz > 1e6:
            warn.append(msg + " - 1 MHz (busSpeed 1000000000000) recommended for hand wiring + ribbon")
        else:
            info.append(msg)
        seen: set[str] = set()
        modes: dict[str, set[int]] = {}
        for s in cfg.get("sensors", []):
            name, g = s.get("name", "?"), int(s.get("gpio", 0))
            m = re.search(r"spidev(\d+)\.\d+", s.get("dev", ""))
            if not m:
                err.append(f"ems-chtegt.json {name}: cannot parse dev {s.get('dev')}")
                continue
            bus = f"SPI{m.group(1)}"
            modes.setdefault(s["dev"], set()).add(int(s.get("spiMode", 0)))
            if g <= 0:
                warn.append(f"ems-chtegt.json {name}: kernel chip-select - the HAT uses GPIO chip-selects")
                continue
            part = by_cs.get((bus, g))
            where = f"ems-chtegt.json {name} ({bus} CS GPIO{g})"
            if part is None:
                off_hat(where, g)
                continue
            seen.add(part.ref)
            label = part.function.split()[-1]
            if label.lower() != name.lower():
                warn.append(f"{where}: HAT channel is {part.ref} {label} - names differ")
            if not s.get("kind", "").startswith("MAX31856"):
                warn.append(f"{where}: config kind {s.get('kind')} but the HAT fits a MAX31856 - set kind "
                            f"MAX31856K (J/T as needed) and spiMode 1 on every sensor of {s['dev']}")
            elif int(s.get("spiMode", 0)) not in (1, 3):
                err.append(f"{where}: MAX31856 needs spiMode 1 or 3, config has {s.get('spiMode')}")
            else:
                info.append(f"{where}: matches {part.ref} {label}")
        for dev, ms in modes.items():
            if len(ms) > 1:
                warn.append(f"ems-chtegt.json {dev}: mixed spiMode {sorted(ms)} - rb-ems-go opens each "
                            f"spidev once, with the first sensor's mode")
        for q in spi_parts:
            if q.ref not in seen:
                warn.append(f"{q.ref} {q.function}: no matching sensor in ems-chtegt.json")

    adc = load_json("adc/ems-adc.json")
    if adc:
        found: dict[tuple[str, int], list[str]] = {}
        for s in adc.get("sensors", []):
            if s.get("kind") != "ADS1115":
                continue
            bus = "I2C" + str(int(str(s.get("dev", "1")).removeprefix("i2c-")))
            found.setdefault((bus, int(s["addr"], 16)), []).append(s.get("name", "?"))
        for (bus, addr), names in found.items():
            hits = [q.ref for q in p.parts.values()
                    if "ADS1115" in q.part and q.bus == bus and q.i2c_addr == addr and not q.dnp]
            where = f"ems-adc.json {', '.join(names)} ({bus} 0x{addr:02X})"
            if hits:
                info.append(f"{where}: matches {hits[0]}")
            else:
                err.append(f"{where}: no ADS1115 at that bus/address on the HAT")

    for rel, key in (("gpio/ems-gpio.json", "channel"), ("rpm/ems-rpm.json", "gpio")):
        cfg = load_json(rel)
        for s in (cfg or {}).get("sensors", []):
            off_hat(f"{rel} {s.get('name', '?')}", int(s.get(key, -1)))
    return err, warn, info


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd not in ("check", "gen", "rbems"):
        print(__doc__)
        return 2
    p = load()
    if cmd == "rbems":
        rbdir = rbems_dir(argv[2] if len(argv) > 2 else None)
        if not rbdir.is_dir():
            print(f"rb-ems-go not found at {rbdir} (pass a path or set RB_EMS_GO)")
            return 2
        err, warn, info = rbems(p, rbdir)
        for tag, rows in (("OK   ", info), ("WARN ", warn), ("ERROR", err)):
            for row in rows:
                print(f"{tag} {row}")
        print(f"rb-ems-go at {rbdir}: {len(err)} error(s), {len(warn)} warning(s)")
        return 1 if err else 0
    err, warn = check(p)
    for w in warn:
        print(f"WARN  {w}")
    for e in err:
        print(f"ERROR {e}")
    fitted = sum(1 for q in p.parts.values() if not q.dnp)
    print(f"{len(p.parts)} parts ({fitted} fitted), {len(p.nets)} nets, {len(p.nodes)} nodes: "
          f"{len(err)} error(s), {len(warn)} warning(s)")
    if err:
        return 1
    if cmd == "gen":
        GEN.mkdir(parents=True, exist_ok=True)
        (GEN / "gpio-map.md").write_text(gen_gpio_map(p), encoding="utf-8")
        (GEN / "wiring-list.md").write_text(gen_wiring_list(p), encoding="utf-8")
        print(f"wrote {GEN.relative_to(ROOT)}/gpio-map.md, wiring-list.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

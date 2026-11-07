# KiCad project (Rev A) - placeholder

The Rev A project doesn't exist yet. The custom PCB starts once the DIY build (Rev 0) passes every bring-up stage.
Plan: [docs/06-custom-pcb.md](../../docs/06-custom-pcb.md).

[rb01hat-concept/](rb01hat-concept/README.md) is a generated visualisation of that plan, with 3D renders. It is not
the Rev A design and must not be fabricated.

Planned layout:

```
hardware/kicad/
  rb01hat/               main HAT+ board (outline A)
    rb01hat.kicad_pro
    rb01hat.kicad_sch    hierarchical sheets: power, imu, env, thermocouples, pressure, adc, eeprom, header
    rb01hat.kicad_pcb
    production/          fab outputs (git-ignored; regenerate)
  rb01hat-ext/           EGT bank daughterboard (outline A)
  lib/                   project symbols, footprints and 3D models
```

Rules for when work starts:

- Reference designators and net names follow [hardware/netlist.csv](../netlist.csv). When the schematic changes,
  update the CSVs in the same change and keep `make check` green, so the bring-up script stays valid.
- Keep ERC and DRC clean before any fab order. Use the fab's own design-rule preset.

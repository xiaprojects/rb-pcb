# RB01HAT - Raspberry Pi 5 sensor HAT

A HAT for the Raspberry Pi 5 in the RB-04 EMS. Its pin mapping follows
[rb-ems-go](docs/07-rb-ems-alignment.md). Devices, in priority order:

1. **ICM-20948**: 9-axis IMU
2. **BME680**: temperature, humidity, pressure, gas
3. **4x MAX31856**: CHT1-CHT4 thermocouples (SPI1)
4. **MS4525DO**: differential pressure (airspeed)
5. **ADS1115**: 4-channel 16-bit ADC (I2C0, 5 V behind a level translator)
6. **4x MAX31856**: EGT1-EGT4 thermocouples (SPI0), on an extension plate over USB/Ethernet

Rev 0 is a DIY build on a proto HAT with breakout modules. Rev A will be a custom PCB in the HAT form factor.

## Quick start

```bash
make check      # validate hardware/*.csv
make docs       # regenerate docs/generated/ (GPIO map, wiring list)
make rbems      # cross-check against the rb-ems-go JSON configs
make pins       # resolved pin map
```

On the Pi (after the setup in [docs/05-bringup.md](docs/05-bringup.md)):

```bash
python3 software/bringup/rb01hat_bringup.py all
```

## Documentation

| Doc | Content |
|---|---|
| [01 Requirements](docs/01-requirements.md) | Requirements, priority interpretation, assumptions, open questions |
| [02 Architecture](docs/02-architecture.md) | Buses, GPIO allocation, pull-ups, power, software |
| [03 Mechanical](docs/03-mechanical.md) | Pi 5 dimensions, stack height, zone plan, extension |
| [04 DIY build](docs/04-diy-build.md) | Step-by-step build using the jumper kit, build stages |
| [05 Bring-up](docs/05-bringup.md) | Checks, Pi setup, test script, troubleshooting |
| [06 Custom PCB](docs/06-custom-pcb.md) | Rev A plan and HAT+ checklist |
| [07 RB-EMS alignment](docs/07-rb-ems-alignment.md) | Mapping vs rb-ems-go, discrepancies, changes rb-ems-go needs |
| [08 RB-01 system](docs/08-rb01-system.md) | High-level RB-01 diagram: displays, HATs, USB, radios, network |
| [GPIO map](docs/generated/gpio-map.md) | Generated pin, address and chip-select tables |
| [Wiring list](docs/generated/wiring-list.md) | Generated wire-by-wire checklist |
| [References](docs/references.md) | Datasheets and links |

Design data lives in [hardware/](hardware/). Contributor and AI-assistant rules are in [CLAUDE.md](CLAUDE.md).

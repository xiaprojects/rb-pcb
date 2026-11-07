PY ?= python3
RB_EMS_GO ?= ../../rb-ems-go

.PHONY: check docs pins rbems clean

## Validate hardware/*.csv (pin conflicts, reserved GPIOs, I2C clashes, supplies, BOM coverage)
check:
	$(PY) tools/netlist.py check

## Validate, then regenerate docs/generated/* (GPIO map, wiring list, RB-01 system diagram)
docs:
	$(PY) tools/netlist.py gen
	$(PY) tools/rb01_diagram.py

## Cross-check the HAT pin mapping against the rb-ems-go JSON configs
rbems:
	$(PY) tools/netlist.py rbems $(RB_EMS_GO)

## Print the resolved pin map (same view the bring-up script uses)
pins:
	$(PY) software/bringup/rb01hat_bringup.py pins

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

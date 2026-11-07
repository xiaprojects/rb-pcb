# Extension plate (EGT bank carrier) - specification

Status: specification only. No CAD yet. When the CAD is made, put it in this folder (a parametric OpenSCAD or
FreeCAD source plus the exported STL), and update this page with the as-built dimensions.

## Function

Holds the EGT bank (U9-U12 = EGT1-EGT4, priority 6) over the Pi's USB/Ethernet block. It is the "plastic extension" allowed by
requirement R4.

## Geometry (coordinates as in docs/03-mechanical.md; top view, origin at the Pi's top-left corner)

```
            x=55   61.5  65                                 88
   y=0       +------(o)---+-----------------------------------+
             | ear H2     |  carrier perfboard (~22 x 56)     |
             +------------+   J12 (2x5)       <- ribbon from J11
                          |   U9  U10 U11 U12  vertical cards |
                          |   (EGT1 EGT2 EGT3 EGT4)           |
                          |   == rib ==                       |
             +------------+                                   |
             | ear H4     |   [ ] [ ] cable-tie slots  ->     |
   y=56      +------(o)---+-----------------------------------+
```

| Parameter | Value | Notes |
|---|---|---|
| Material | PETG or ASA | Not PLA: it sits close to the warm RP1/Ethernet area. |
| Thickness | 3 mm, plus two 5 mm ribs along x | Stiffness under thermocouple cable pull. |
| Footprint | x 65 to 88, y 0 to 56 | Ends at the jack faces (x = 88), so plugs stay accessible. |
| Fixing | Two ears reaching H2 (61.5, 3.5) and H4 (61.5, 52.5) over the HAT, fixed with the HAT's own M2.5 screws (use longer M2.5 x 10-12 mm) | Ears are 7 mm diameter pads. Leave the HAT area between them free for J11 and the ribbon. |
| Height | Plate rests on top of the HAT at the ears. With stack S1 the plate bottom is about 21.5 mm above the Pi PCB, about 5 mm above the USB stack. | With S2 the margin drops to about 1.5 mm: **measure the USB height**. |
| Carrier | Perfboard about 22 x 56 mm on four M2.5 x 6 mm standoffs (heat-set inserts in the plate) | Holds J12 and the four vertical MAX31856 cards at 10.16 mm pitch. |
| Strain relief | Cable-tie slots on the outer (x = 88) edge, one per thermocouple | Thermocouple leads must never pull on the module terminals. |
| Labels | Embossed EGT1-EGT4 next to each card | Must match the rb-ems-go names (egt1-egt4). |

## Checks after printing

- [ ] All USB and Ethernet plugs insert fully.
- [ ] The Active Cooler fan cable isn't pinched (with S1 it passes under the plate).
- [ ] The ribbon from J11 to J12 runs without tension or sharp folds.
- [ ] The plate doesn't flex when a thermocouple lead is pulled.

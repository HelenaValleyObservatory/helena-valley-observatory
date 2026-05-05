# Helena Valley Observatory — Flow Lab

Passive atmospheric wind sensing using ADS-B aircraft telemetry.

A fixed ground receiver logs ADS-B broadcasts from overflying aircraft.
Reciprocal flight pairs — aircraft flying opposing tracks at similar
times and altitudes — encode the wind field through their groundspeed
difference. This pipeline extracts, validates, and reports those wind
estimates daily.

**Results from Helena, Montana (100-day baseline):**
- Jet-level wind direction: ~14.3° mean angular error vs ERA5 reanalysis
  on zonal flow days (N=21, AMDAR operational target: 10–20°)
- Day-to-day jet direction consistency: R=0.954
- Terrain channeling index: 0.855 (strong valley signature)
- Surface expression of January–February 2026 SSW event detected

Published on RTL-SDR.com: [link when live]

---

## Hardware Requirements

- RTL-SDR Blog V4 (or compatible ADS-B receiver)
- 1090MHz antenna (stock dipole works — that's what these results used)
- Linux machine running readsb
- ~50MB/day storage for archive

## Software Requirements

```bash
OBSERVATORY FLOW LABORATORY — DAILY REPORT
Date     : 2026-02-28
...
FLOW REGIME: RESOLVED_MARGINAL
VERTICAL WIND PROFILE:
Layer    Speed  Direction  Shear    N      Q
BL        24kt   100° (E)    —     64   0.07
JET       30kt    96° (E)  20kt    73   0.11
...

---

## Limitations

- Passive inference only — no radar, no radiosonde, no tower data
- Wind speed estimates carry higher uncertainty than direction
- Requires sufficient reciprocal traffic geometry (not all days qualify)
- Results are site-specific — Helena findings don't transfer without
  your own baseline
- Not validated for operational use

---

## License

MIT License — see LICENSE file

---

## Citation

If you use this code in research, please cite:

Larson, M. (2026). Listening to the Jet Stream: 100 Days of Wind
Sensing with Stock RTL-SDR Hardware. RTL-SDR.com.

---

## Contact

Matt Larson — Helena Valley Observatory — Helena, Montana
Code available on request for collaboration inquiries.

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
- 1090MHz antenna (stock dipole works — that is what these results used)
- Linux machine running readsb
- ~50MB/day storage for archive

---

## Software Requirements

```bash
pip install numpy pandas pyarrow
```

readsb must be running and writing aircraft.json to a known path.

---

## Installation

```bash
git clone https://github.com/HelenaValleyObservatory/helena-valley-observatory
cd helena-valley-observatory
cp config/observatory.cfg.example config/observatory.cfg
nano config/observatory.cfg
```

---

## Configuration

Edit `config/observatory.cfg` before running anything:

```ini
[observatory]
data_root       = /your/data/path        # where archives will be stored
receiver_lat    = 46.5890                # your receiver latitude
receiver_lon    = -112.0391              # your receiver longitude
airport_name    = KHLN                   # nearest airport identifier
field_elev_ft   = 3877                   # field elevation MSL
valley_axis_deg = 75.0                   # your local terrain axis (degrees)

[readsb]
aircraft_json   = /run/readsb/aircraft.json
poll_interval   = 5
```

**valley_axis_deg** is the most important site-specific parameter.
Set it to the primary terrain axis of your local valley or corridor.
If you are not in a valley, set it to your prevailing wind direction.

---

## Usage

**Step 1 — Start logging:**
```bash
python logger/aircraft_logger.py
```

Logs all aircraft observations to daily JSONL files in `data/aircraft/`.
Run continuously (systemd service recommended). Let it run for 30 days
before attempting wind analysis.

**Step 2 — Run the Flow Lab pipeline for a date:**
```bash
bash bin/fl_run.sh 20260228
```

Runs four stages:
1. `fl_segment.py` — extract straight-flight segments
2. `fl_wind.py` — solve wind vectors from reciprocal pairs
3. `fl_terrain.py` — terrain channeling and turbulence proxy
4. `fl_report.py` — generate daily text brief

Output: `data/briefs/flowlab_YYYYMMDD.txt`

**Step 3 — Automate with cron:**
```bash
# Run nightly at 00:30 UTC for previous day
30 0 * * * bash /path/to/helena-valley-observatory/bin/fl_run.sh --yesterday
```

---

## Sample Output
OBSERVATORY FLOW LABORATORY — DAILY REPORT
Date     : 2026-02-28
FLOW REGIME: RESOLVED_MARGINAL
VERTICAL WIND PROFILE:
Layer    Speed  Direction  Shear    N      Q
BL        24kt   100 E       —     64   0.07
JET       30kt    96 E     20kt    73   0.11

---

## Methodology

The reciprocal pair wind solver works as follows:

If two aircraft fly opposing tracks (e.g. 090 and 270 degrees) at similar
times and altitudes, one experiences a tailwind and one a headwind.
The difference in their groundspeeds divided by two gives the wind
component along that axis — without measuring airspeed.

The solver accounts for aircraft class. Wind direction estimates are
reported with explicit confidence metrics. Days where geometry or flow
conditions invalidate the method are flagged as UNRESOLVED rather than
producing incorrect estimates. The system produces no output on days
where geometry or flow conditions invalidate the method.

Full methodology: see published article on RTL-SDR.com

---

## Validation

Cross-check your results against:
- **ERA5 reanalysis** — Copernicus Climate Data Store (free)
  https://cds.climate.copernicus.eu
- **IGRA2 radiosonde data** — nearest upper-air station
  https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive

Do not skip the validation step. The wind solver will produce
plausible-looking results that may be wrong without external validation.

---

## Limitations

- Passive inference only — no radar, no radiosonde, no tower data
- Wind speed estimates carry higher uncertainty than direction
- Requires sufficient reciprocal traffic geometry (not all days qualify)
- Results are site-specific — Helena findings do not transfer without
  your own 30-day baseline
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

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

Published on RTL-SDR.com: https://www.rtl-sdr.com/guest-post-listening-to-the-jet-stream-100-days-of-wind-sensing-with-stock-rtl-sdr-hardware/

---

## Hardware Requirements

- RTL-SDR Blog V4 (or compatible ADS-B receiver)
- 1090MHz antenna (stock dipole works — that is what these results used)
- Linux machine running readsb
- ~50MB/day storage for archive

---

## Software Requirements

    pip install numpy pandas pyarrow

readsb must be running and writing aircraft.json to a known path.

---

## Installation

    git clone https://github.com/HelenaValleyObservatory/helena-valley-observatory
    cd helena-valley-observatory
    cp config/observatory.cfg.example config/observatory.cfg
    nano config/observatory.cfg

---

## Configuration

Edit `config/observatory.cfg` before running anything:

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

**valley_axis_deg** is the most important site-specific parameter.
Set it to the primary terrain axis of your local valley or corridor.
If you are not in a valley, set it to your prevailing wind direction.

You can also set the `HELENA_DATA` environment variable to point to your
data directory, which overrides the config file.

---

## Usage

**Step 1 — Start logging:**

    python logger/aircraft_logger.py

Logs all aircraft observations to daily JSONL files in `data/aircraft/`.
Run continuously (systemd service recommended). Let it run for 30 days
before attempting wind analysis.

**Step 2 — Run the Flow Lab pipeline for a date:**

    bash bin/fl_run.sh 20260228

Runs five stages:
1. `fl_segment.py` — extract straight-flight segments from raw JSONL
2. `fl_stepa.py` — reciprocal-pair wind solver (Step A gold set)
3. `fl_wind.py` — aggregate wind vectors by altitude layer
4. `fl_terrain.py` — terrain channeling index and turbulence proxy
5. `fl_report.py` — generate daily text brief

Output: `data/briefs/flowlab_YYYYMMDD.txt`

**Step 3 — Automate with cron:**

    # Run nightly at 00:30 UTC for previous day
    30 0 * * * bash /path/to/helena-valley-observatory/bin/fl_run.sh --yesterday

---

## Pipeline Scripts

| Script | What it does |
|---|---|
| `logger/aircraft_logger.py` | Continuous ADS-B capture to daily JSONL |
| `bin/fl_segment.py` | Extract level-flight segments from JSONL |
| `bin/fl_stepa.py` | **Reciprocal-pair wind solver** — the physics engine |
| `bin/fl_wind.py` | Aggregate wind vectors by altitude layer (BL/LL/MID/UPPER/JET) |
| `bin/fl_terrain.py` | Terrain channeling index and KTI turbulence proxy |
| `bin/fl_report.py` | Daily brief with flow regime classification |
| `bin/fl_run.sh` | Nightly driver — runs all stages for a given date |
| `bin/council.py` | Observer Council — ten automated analytical observers |

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

The reciprocal pair wind solver (`fl_stepa.py`) works as follows:

If two aircraft fly opposing tracks (e.g. 090° and 270°) at similar
times and altitudes, one experiences a tailwind and one a headwind.
The difference in their groundspeeds divided by two gives the wind
component along that axis — without measuring airspeed.

    GS1 + GS2 = 2 * [U, V]   (midpoint estimator, when TAS1 ≈ TAS2)

When aircraft classes differ, the full system is solved using groundspeed
magnitude constraints and heading geometry. Each pair receives a quality
score based on heading difference, time separation, spatial separation,
and TAS similarity. Output includes bootstrap confidence intervals and
vector strength R per altitude layer.

The solver accounts for aircraft class. Wind direction estimates are
reported with explicit confidence metrics. Days where geometry or flow
conditions invalidate the method are flagged as UNRESOLVED rather than
producing incorrect estimates.

Full methodology: see published article on RTL-SDR.com

---

## Observer Council

The repo includes an interpretive architecture built on top of the
Flow Lab: ten automated observers, each named after a real astronomer,
each wired to different data streams, each asking a different question.

    observers/
      barnard/    Deep pattern detection — 90-day seasonal arcs
      brahe/      Quality control — instrument health before trusting output
      cannon/     Classification catalog — counts, sorts, complete record
      galileo/    Anomaly detection — flags deviations from expected patterns
      herschel/   Discovery sentinel — first-ever events in the archive
      hevelius/   Celestial cartography — Sun, Moon, planets above Helena
      kepler/     Mathematical laws — distributions, extremes, trends
      moore/      Narrative generation — turns numbers into plain language
      rubin/      Inference from absence — reads the silences in the data
      sagan/      Cosmic perspective — places the work in context

Run a council session:

    python bin/council.py

Sessions are saved to `almanac/`. The observatory remembers.

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
https://www.rtl-sdr.com/guest-post-listening-to-the-jet-stream-100-days-of-wind-sensing-with-stock-rtl-sdr-hardware/

---

## Contact

Matt Larson — Helena Valley Observatory — Helena, Montana
one2three4five6789@icloud.com

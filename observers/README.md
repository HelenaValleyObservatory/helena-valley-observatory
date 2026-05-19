# The Observer Council

The Helena Valley Observatory runs ten automated observers. Each session
they examine the same archive and report what they find. Their perspectives
are combined into a council session saved to the almanac.

This is not a monitoring dashboard. It is an interpretive architecture.

---

## Why Ten Observers

A single analysis script optimizes for one thing. An observatory needs
to optimize for many things simultaneously — quality, pattern, anomaly,
narrative, absence, law, discovery, classification, position, meaning.

Each observer is wired to different data streams and asks a different
kind of question. Their disagreements are as informative as their agreements.

The names were chosen deliberately. Each namesake's actual historical work
matches the function assigned to their observer.

---

## The Council

### Barnard — The Deep Observer
Named for E.E. Barnard, whose patient decades of visual observation
revealed what photographic surveys missed.

Wired to 90-day flow lab archive. Finds patterns that only emerge from
months of watching — seasonal arcs, weekly rhythms, long-period cycles.
Barnard does not report today. Barnard reports what today means in context.

### Brahe — The Quality Controller
Named for Tycho Brahe, whose obsessive measurement precision made
Kepler's laws possible.

Wired to system health and signal quality. Verifies the instrument before
trusting the instrument's output. If Brahe flags a warning, everything
downstream is suspect.

### Cannon — The Classifier
Named for Annie Jump Cannon, who classified 350,000 stars by hand and
built the system still in use today.

Wired to the full shear profile history and aircraft database. Organizes
everything into structured catalogs. Cannon does not interpret — Cannon
counts, sorts, and presents the complete record.

### Galileo — The Anomaly Hunter
Named for Galileo Galilei, who pointed a telescope at the sky and saw
things that were not supposed to be there.

Wired to flow lab output. Flags deviations from expected atmospheric
patterns. When everything is normal, Galileo says so. When something
is anomalous, Galileo names it.

### Herschel — The Discovery Sentinel
Named for Caroline Herschel, who discovered eight comets and was the
first woman to receive a Gold Medal of the Royal Astronomical Society.

Wired to the aircraft database and flow lab. Watches for first-ever
events — new aircraft types, new routes, new atmospheric signatures.
Herschel tracks what the archive has never seen before.

### Hevelius — The Cartographer
Named for Johannes Hevelius, who built the most accurate star atlas
of the 17th century and mapped 1,564 stars without a telescope.

Wired to celestial position calculations. Knows where the Sun, Moon,
and planets are above Helena at every session. Hevelius reminds the
council that the observatory exists in a specific place under a specific sky.

### Kepler — The Mathematician
Named for Johannes Kepler, who found the laws governing planetary motion
hidden in Brahe's observations.

Wired to the jet spine and wind physics. Derives mathematical laws from
the archive — distributions, extremes, trends, seasonal patterns.
Kepler finds the equations the atmosphere is following.

### Moore — The Storyteller
Named for Patrick Moore, who explained the universe to the public for
over fifty years without ever talking down to them.

Wired to today's atmospheric data. Turns numbers into prose. Moore's
output changes every day based on actual conditions — the jet speed,
the boundary layer direction, the decoupling angle. When the valley
locks and the jet wanders, Moore says so in plain language.

### Rubin — The Inferrer
Named for Vera Rubin, who discovered dark matter by noticing that
galaxies were not rotating the way they should.

Wired to flow lab gaps and missing data. Asks what is absent and why.
Days with no output are not failures to ignore — they are data points
about atmospheric conditions that prevent measurement. Rubin reads
the silences.

### Sagan — The Philosopher
Named for Carl Sagan, who understood that science without wonder
is just bookkeeping.

Wired to the full findings archive and real observatory data. Closes
every session by placing the observatory's work in context — the days
of operation, the aircraft witnessed, the jet stream speed above Helena
right now, the planets visible tonight. Sagan asks what it means.

---

## A Council Session

The council convenes via bin/council.py. Each observer runs independently,
examines its assigned data, and reports. Sessions are saved to almanac/.

Example output from session council_20260518_2039.txt:

    [Barnard] Deep patterns across 90 days:
      BL wind seasonal arc (70 days): Feb=94 -> Mar=116 -> Apr=105 -> May=137
      Strong reversals (>120): 12 days detected, most recent: 20260506
      Jet weekly rhythm: strongest on Sun (62kt), weakest on Fri (54kt)

    [Rubin] Inference from Absence:
      17/90 days have no Flow Lab output. What atmospheric conditions
      prevented processing?
      46 days with BL/JET coupling (<30 difference). Finding 005: the valley
      did not break, the jet returned to easterly. Valley locks, jet wanders.

    [Sagan] Cosmic Perspective:
      We are a way for the cosmos to know itself.

      This observatory has operated for 132 days.
      It has witnessed 6,985 unique aircraft.
      It has filed 14 formal findings.

      The jet stream over Helena right now: 17.1kt.
      A river of air, 35,000 feet above the valley,
      measured by the ground speeds of passing airliners.



---

## Running the Council

    cd /path/to/helena-valley-observatory
    python bin/council.py

Sessions are saved automatically to almanac/council_YYYYMMDD_HHMM.txt.

---

## Design Philosophy

Each observer is a Python class with two methods: observe() and report().
observe() reads data and returns structured findings. report() formats
them for the session output. They are independent — one observer's failure
does not affect the others.

The council does not vote. It does not reach consensus. It presents ten
perspectives and leaves synthesis to the reader. The disagreements between
observers — Galileo seeing nothing anomalous on a day Rubin flags as
suspicious — are the most scientifically interesting outputs.

The almanac is a permanent record. Every session is saved. The observatory
remembers.

---

## Repository Structure

    observers/
      README.md              this document
      barnard/observer.py    deep pattern detection
      brahe/observer.py      quality control
      cannon/observer.py     classification catalog
      galileo/observer.py    anomaly detection
      herschel/observer.py   discovery sentinel
      hevelius/observer.py   celestial cartography
      kepler/observer.py     mathematical laws
      moore/observer.py      narrative generation
      rubin/observer.py      inference from absence
      sagan/observer.py      cosmic perspective

    almanac/
      council_YYYYMMDD_HHMM.txt   permanent session records

---

Helena Valley Observatory, Helena, Montana
Operational since 2026-01-17
Build the baseline. Then we find the truth.

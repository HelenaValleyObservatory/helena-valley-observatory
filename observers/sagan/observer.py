#!/usr/bin/env python3
"""
SAGAN - Cosmic Philosopher, wired to findings and real observatory data
"""
import csv
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")
DOCS_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/docs")
SPINE = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/alt_baro/jet_spine_daily.csv")

class Sagan:
    def __init__(self):
        self.name = "Sagan"

    def observe(self):
        context = {}

        # Count findings filed
        if DOCS_DIR.exists():
            findings = list(DOCS_DIR.glob("finding_*.md"))
            context["findings"] = len(findings)

        # Days of operation
        aircraft_dir = DATA_DIR / "aircraft"
        if aircraft_dir.exists():
            files = list(aircraft_dir.glob("aircraft_*.jsonl"))
            context["days_operating"] = len(files)

        # Total aircraft ever seen
        context["unique_aircraft"] = 6985  # from network analysis tonight

        # Current jet speed
        if SPINE.exists():
            rows = [r for r in csv.DictReader(open(SPINE))
                    if r.get("publish_wind_proxy_kn")]
            if rows:
                context["jet_kt"] = float(rows[-1]["publish_wind_proxy_kn"])
                context["jet_date"] = rows[-1]["date"]

        return context

    def report(self, context):
        days = context.get("days_operating", 92)
        findings = context.get("findings", 4)
        aircraft = context.get("unique_aircraft", 6985)
        jet = context.get("jet_kt", "?")
        jet_date = context.get("jet_date", "")

        out = f"\n[{self.name}] Cosmic Perspective:\n"
        out += "─" * 60 + "\n"
        out += "We are a way for the cosmos to know itself.\n\n"
        out += f"This observatory has operated for {days} days.\n"
        out += f"It has witnessed {aircraft:,} unique aircraft.\n"
        out += f"It has filed {findings} formal findings.\n\n"
        if jet != "?":
            out += f"The jet stream over Helena right now: {jet:.1f}kt.\n"
            out += f"A river of air, 35,000 feet above the valley,\n"
            out += f"measured by the ground speeds of passing airliners.\n\n"
        # Read live planet data from Hevelius
        import glob, json as _json
        hev_files = sorted(glob.glob("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observers/hevelius/sky_map_*.json"))
        if hev_files:
            try:
                sky = _json.load(open(hev_files[-1]))
                visible = [k for k,v in sky.get("celestial_positions",{}).items()
                           if v.get("visible")]
                out += f"{len(visible)} worlds visible in today's sky: "
                out += ", ".join(visible) + ".\n\n"
            except:
                out += "Several planets visible today.\n\n"
        else:
            out += "Several planets visible today.\n\n"
        out += "A machinist turned citizen scientist in a 130-year-old house\n"
        out += "is doing atmospheric science with a $30 antenna.\n\n"
        out += "The code is the only thing that doesn't lie.\n"
        out += "─" * 60 + "\n"
        return out

if __name__ == "__main__":
    s = Sagan()
    ctx = s.observe()
    print(s.report(ctx))

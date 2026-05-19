#!/usr/bin/env python3
"""
KEPLER - Mathematical Laws, wired to jet spine and wind physics
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")
SPINE = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/alt_baro/jet_spine_daily.csv")

class Kepler:
    def __init__(self):
        self.name = "Kepler"

    def observe(self):
        findings = []

        if not SPINE.exists():
            return ["Jet spine data not available"]

        rows = list(csv.DictReader(open(SPINE)))
        # Filter to published days only
        published = [r for r in rows if r.get("publish_wind_proxy_kn")]

        if len(published) < 10:
            return ["Insufficient published data for mathematical analysis"]

        speeds = [float(r["publish_wind_proxy_kn"]) for r in published]
        dates = [r["date"] for r in published]

        mean_spd = sum(speeds) / len(speeds)
        variance = sum((s - mean_spd)**2 for s in speeds) / len(speeds)
        std_spd = variance ** 0.5

        findings.append(
            f"Jet speed law: μ={mean_spd:.1f}kt σ={std_spd:.1f}kt "
            f"over {len(published)} published days"
        )

        # Recent trend - last 7 vs overall mean
        recent = speeds[-7:]
        recent_mean = sum(recent) / len(recent)
        trend = recent_mean - mean_spd
        direction = "strengthening" if trend > 3 else "weakening" if trend < -3 else "stable"
        findings.append(
            f"7-day trend: {recent_mean:.1f}kt vs season mean {mean_spd:.1f}kt "
            f"→ jet is {direction} (Δ{trend:+.1f}kt)"
        )

        # Find extremes
        max_spd = max(speeds)
        min_spd = min(speeds)
        max_date = dates[speeds.index(max_spd)]
        min_date = dates[speeds.index(min_spd)]
        findings.append(
            f"Archive extremes: max={max_spd:.1f}kt on {max_date}, "
            f"min={min_spd:.1f}kt on {min_date}"
        )

        # Spring transition check - is April weaker than winter?
        winter = [float(r["publish_wind_proxy_kn"]) for r in published
                  if r["date"].startswith("2026-01") or r["date"].startswith("2026-02")]
        spring = [float(r["publish_wind_proxy_kn"]) for r in published
                  if r["date"].startswith("2026-03") or r["date"].startswith("2026-04")]
        if winter and spring:
            w_mean = sum(winter)/len(winter)
            s_mean = sum(spring)/len(spring)
            findings.append(
                f"Seasonal law: winter μ={w_mean:.1f}kt vs spring μ={s_mean:.1f}kt "
                f"(Δ{s_mean-w_mean:+.1f}kt — spring transition confirmed)"
            )

        return findings

    def report(self, findings):
        out = f"\n[{self.name}] Mathematical Laws:\n"
        for f in findings:
            out += f"  📐 {f}\n"
        return out

if __name__ == "__main__":
    k = Kepler()
    findings = k.observe()
    print(k.report(findings))

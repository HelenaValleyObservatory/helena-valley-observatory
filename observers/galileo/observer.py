#!/usr/bin/env python3
"""
GALILEO - Anomaly Hunter, wired to Flow Lab
Flags deviations from expected atmospheric patterns
"""
import json, csv, os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")

class Galileo:
    def __init__(self):
        self.name = "Galileo"

    def observe(self):
        anomalies = []

        # Load last 7 days of shear profiles
        bl_jet_angles = []
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            sp = DATA_DIR / "flowlab" / date / "shear_profile.csv"
            if not sp.exists():
                continue
            try:
                rows = {r["alt_bin"]: r for r in csv.DictReader(open(sp))}
                bl = rows.get("BL")
                jet = rows.get("JET")
                if bl and jet and bl.get("wind_dir_deg") and jet.get("wind_dir_deg"):
                    bl_dir = float(bl["wind_dir_deg"])
                    jet_dir = float(jet["wind_dir_deg"])
                    diff = abs(bl_dir - jet_dir)
                    if diff > 180: diff = 360 - diff
                    bl_jet_angles.append((date, diff, bl_dir, jet_dir))
            except:
                continue

        if bl_jet_angles:
            # Flag strong reversals (>120 degrees)
            for date, angle, bl_dir, jet_dir in bl_jet_angles:
                if angle > 120:
                    anomalies.append(
                        f"REVERSAL {date}: BL={bl_dir:.0f}° vs JET={jet_dir:.0f}° "
                        f"(decoupling={angle:.0f}°) — exceeds 120° threshold"
                    )

            # Flag if today's jet is unusually weak
            today_sp = DATA_DIR / "flowlab" / datetime.now().strftime("%Y%m%d") / "shear_profile.csv"
            if today_sp.exists():
                try:
                    rows = {r["alt_bin"]: r for r in csv.DictReader(open(today_sp))}
                    jet = rows.get("JET")
                    if jet and jet.get("wind_spd_kt"):
                        spd = float(jet["wind_spd_kt"])
                        if spd < 10:
                            anomalies.append(
                                f"JET COLLAPSE today: {spd:.1f}kt — "
                                f"below 10kt threshold (SSW signature)"
                            )
                except:
                    pass

        # Load gold summary for regime anomalies
        gold = DATA_DIR / "gold" / "gold_summary.csv"
        if gold.exists():
            try:
                rows = list(csv.DictReader(open(gold)))
                recent = rows[-7:] if len(rows) >= 7 else rows
                not_zonal = [r for r in recent if r.get("regime") == "NOT_ZONAL"]
                if len(not_zonal) >= 3:
                    anomalies.append(
                        f"REGIME ALERT: {len(not_zonal)}/7 recent days NOT_ZONAL "
                        f"— persistent decoupling pattern"
                    )
            except:
                pass

        return anomalies

    def report(self, anomalies):
        if not anomalies:
            return f"\n[{self.name}] All atmospheric patterns within expected bounds.\n"
        out = f"\n[{self.name}] {len(anomalies)} atmospheric anomaly(ies) detected:\n"
        for a in anomalies:
            out += f"  • {a}\n"
        out += f"  Question: What forcing mechanism drives these deviations?\n"
        return out

if __name__ == "__main__":
    g = Galileo()
    obs = g.observe()
    print(g.report(obs))

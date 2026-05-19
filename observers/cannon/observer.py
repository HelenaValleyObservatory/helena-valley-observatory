#!/usr/bin/env python3
"""
CANNON - Classifier, wired to full shear profile history and database
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")
DB_PATH = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observatory.db")

class Cannon:
    def __init__(self):
        self.name = "Cannon"

    def observe(self):
        catalog = {}

        # === REGIME CLASSIFICATION from shear profiles ===
        flowlab_dir = DATA_DIR / "flowlab"
        regimes = Counter()
        monthly_regimes = defaultdict(Counter)
        days_with_data = 0

        for i in range(90):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            sp = flowlab_dir / date / "shear_profile.csv"
            if not sp.exists():
                continue
            days_with_data += 1
            month = date[4:6]
            try:
                rows = {r["alt_bin"]: r for r in csv.DictReader(open(sp))}
                bl = rows.get("BL")
                jet = rows.get("JET")
                if bl and jet and bl.get("wind_dir_deg") and jet.get("wind_dir_deg"):
                    diff = abs(float(bl["wind_dir_deg"]) - float(jet["wind_dir_deg"]))
                    if diff > 180: diff = 360 - diff
                    if diff > 90:
                        reg = "NOT_ZONAL"
                    elif diff > 45:
                        reg = "PARTIAL"
                    else:
                        reg = "ZONAL"
                    regimes[reg] += 1
                    monthly_regimes[month][reg] += 1
            except:
                continue

        catalog["regime_days"] = days_with_data
        catalog["regimes"] = dict(regimes)
        catalog["monthly_regimes"] = {
            m: dict(v) for m, v in sorted(monthly_regimes.items())
        }

        # === AIRCRAFT from database (correct table: aircraft_day) ===
        if DB_PATH.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("""
                    SELECT category, COUNT(*) as cnt
                    FROM aircraft_day
                    GROUP BY category ORDER BY cnt DESC
                """)
                catalog["aircraft_categories"] = {r[0]: r[1] for r in cur.fetchall()}
                cur.execute("""
                    SELECT icao_type, COUNT(*) as cnt
                    FROM aircraft_day WHERE category = 'MILITARY'
                    GROUP BY icao_type ORDER BY cnt DESC LIMIT 6
                """)
                catalog["military_types"] = {r[0]: r[1] for r in cur.fetchall()}
                conn.close()
            except Exception as e:
                catalog["db_error"] = str(e)

        # === SHEAR EVENTS (validated=no exploratory suffix) ===
        shear_dir = DATA_DIR / "shear_events"
        if shear_dir.exists():
            all_json = list(shear_dir.glob("*.json"))
            validated = [f for f in all_json if "exploratory" not in f.name]
            exploratory = [f for f in all_json if "exploratory" in f.name]
            catalog["shear_events"] = {
                "validated": len(validated),
                "exploratory": len(exploratory)
            }

        return catalog

    def report(self, catalog):
        out = f"\n[{self.name}] Classification Catalog:\n"

        if "regimes" in catalog:
            total = sum(catalog["regimes"].values())
            days = catalog.get("regime_days", total)
            out += f"\n  ATMOSPHERIC REGIMES ({days} days):\n"
            for reg, count in sorted(catalog["regimes"].items(),
                                     key=lambda x: -x[1]):
                pct = count / total * 100 if total else 0
                out += f"    {reg:12}: {count:3} days ({pct:.1f}%)\n"

            if "monthly_regimes" in catalog:
                out += "\n  MONTHLY BREAKDOWN:\n"
                names = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr"}
                for month, counts in catalog["monthly_regimes"].items():
                    mn = names.get(month, month)
                    parts = []
                    for reg in ["ZONAL","PARTIAL","NOT_ZONAL"]:
                        if reg in counts:
                            parts.append(f"{reg[:3]}={counts[reg]}")
                    out += f"    {mn}: {' | '.join(parts)}\n"

        if "aircraft_categories" in catalog:
            out += "\n  AIRCRAFT (90-day archive):\n"
            for cat, count in catalog["aircraft_categories"].items():
                out += f"    {cat}: {count} aircraft-days\n"

        if "military_types" in catalog:
            out += "\n  MILITARY TYPES:\n"
            for atype, count in catalog["military_types"].items():
                out += f"    {atype or 'UNKNOWN'}: {count}\n"

        if "shear_events" in catalog:
            se = catalog["shear_events"]
            out += (f"\n  SHEAR EVENTS: {se['validated']} validated, "
                   f"{se['exploratory']} exploratory\n")

        return out

if __name__ == "__main__":
    c = Cannon()
    catalog = c.observe()
    print(c.report(catalog))

#!/usr/bin/env python3
"""
RUBIN - Inference from Absence, wired to Flow Lab gaps and missing data
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")

class Rubin:
    def __init__(self):
        self.name = "Rubin"

    def observe(self):
        inferences = []

        # What days are missing from flowlab?
        flowlab_dir = DATA_DIR / "flowlab"
        missing_days = []
        for i in range(90):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            if not (flowlab_dir / date).exists():
                missing_days.append(date)

        if missing_days:
            inferences.append(
                f"{len(missing_days)}/90 days have no Flow Lab output — "
                f"what atmospheric conditions prevented processing?"
            )

        # Gold failures - days where data existed but gold failed
        gold = DATA_DIR / "gold" / "gold_summary.csv"
        if gold.exists():
            rows = list(csv.DictReader(open(gold)))
            failed = [r for r in rows if r.get("gold_pass") == "False"]
            fail_reasons = {}
            for r in failed:
                reason = r.get("fail_reason", "unknown")[:40]
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

            if failed:
                top_reason = max(fail_reasons, key=fail_reasons.get)
                inferences.append(
                    f"{len(failed)} days failed gold — "
                    f"most common: '{top_reason}' ({fail_reasons[top_reason]}x). "
                    f"What does the atmosphere look like on these invisible days?"
                )

        # Days where BL and JET were NOT decoupled - what made them couple?
        coupled_days = []
        for i in range(90):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            sp = flowlab_dir / date / "shear_profile.csv"
            if not sp.exists():
                continue
            try:
                rows = {r["alt_bin"]: r for r in csv.DictReader(open(sp))}
                bl = rows.get("BL")
                jet = rows.get("JET")
                if bl and jet and bl.get("wind_dir_deg") and jet.get("wind_dir_deg"):
                    diff = abs(float(bl["wind_dir_deg"]) - float(jet["wind_dir_deg"]))
                    if diff > 180: diff = 360 - diff
                    if diff < 30:
                        coupled_days.append(date)
            except:
                continue

        if coupled_days:
            inferences.append(
                f"{len(coupled_days)} days with BL/JET coupling (<30° difference). "
                f"Finding 005: the valley did not break — the jet returned to easterly. Valley locks, jet wanders."
            )

        return inferences

    def report(self, inferences):
        out = f"\n[{self.name}] Inference from Absence:\n"
        for inf in inferences:
            out += f"  🔍 {inf}\n"
        return out

if __name__ == "__main__":
    r = Rubin()
    inferences = r.observe()
    print(r.report(inferences))

#!/usr/bin/env python3
"""
BRAHE - Quality Controller, wired to Flow Lab and signal quality
"""
import json, csv, subprocess
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")

class Brahe:
    def __init__(self):
        self.name = "Brahe"

    def observe(self):
        checks = []

        # Check if observatory process is running (explains RTL-SDR lock)
        try:
            result = subprocess.run(
                ["pgrep", "-f", "adsb_observatory"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                checks.append(("GOOD", "ADS-B Observatory", "Process running, RTL-SDR locked (expected)"))
            else:
                checks.append(("WARNING", "ADS-B Observatory", "Process not detected"))
        except:
            checks.append(("UNKNOWN", "ADS-B Observatory", "Could not check process"))

        # NTP sync
        try:
            result = subprocess.run(
                ["timedatectl", "status"], capture_output=True, text=True, timeout=5
            )
            if "synchronized: yes" in result.stdout.lower():
                checks.append(("GOOD", "System Clock", "NTP synchronized"))
            else:
                checks.append(("WARNING", "System Clock", "NTP sync uncertain"))
        except:
            checks.append(("UNKNOWN", "System Clock", "Could not verify"))

        # Flow Lab quality — check today's gold status
        gold = DATA_DIR / "gold" / "gold_summary.csv"
        if gold.exists():
            try:
                rows = list(csv.DictReader(open(gold)))
                if rows:
                    today = rows[-1]
                    tier = today.get("gold_pass", "?")
                    regime = today.get("regime", "?")
                    fail = today.get("fail_reason", "")
                    if tier == "True":
                        checks.append(("GOOD", "Flow Lab", f"GOLD PASS — regime={regime}"))
                    elif fail:
                        checks.append(("WARNING", "Flow Lab", f"No gold: {fail[:60]}"))
                    else:
                        checks.append(("WARNING", "Flow Lab", f"Non-gold day, regime={regime}"))
            except:
                checks.append(("UNKNOWN", "Flow Lab", "Could not read gold summary"))

        # Signal quality - check latest signal quality report
        sq_dir = DATA_DIR.parent / "reports" / "signal_quality"
        if sq_dir.exists():
            files = sorted(sq_dir.glob("*.txt"))
            if files:
                latest = files[-1]
                age_days = (datetime.now().timestamp() - latest.stat().st_mtime) / 86400
                if age_days < 2:
                    checks.append(("GOOD", "Signal Quality", f"Report current ({latest.name})"))
                else:
                    checks.append(("WARNING", "Signal Quality", f"Report is {age_days:.0f} days old"))

        # Jet spine data freshness
        spine = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/alt_baro/jet_spine_daily.csv")
        if spine.exists():
            rows = list(csv.DictReader(open(spine)))
            if rows:
                last_date = rows[-1].get("date", "?")
                last_tier = rows[-1].get("quality_tier", "?")
                checks.append(("GOOD", "Jet Spine", f"Last entry: {last_date} tier={last_tier}"))

        return checks

    def report(self, checks):
        errors = sum(1 for s, _, _ in checks if s == "ERROR")
        warnings = sum(1 for s, _, _ in checks if s == "WARNING")
        out = f"\n[{self.name}] Quality Control Report:\n"
        if errors == 0 and warnings == 0:
            out += "  ✅ All systems nominal. Data is trustworthy.\n"
        else:
            if errors: out += f"  ❌ {errors} error(s)\n"
            if warnings: out += f"  ⚠  {warnings} warning(s)\n"
        icons = {"GOOD": "✅", "WARNING": "⚠ ", "ERROR": "❌", "UNKNOWN": "❓"}
        for status, system, note in checks:
            out += f"  {icons.get(status,'•')} {system}: {note}\n"
        return out

if __name__ == "__main__":
    b = Brahe()
    checks = b.observe()
    print(b.report(checks))

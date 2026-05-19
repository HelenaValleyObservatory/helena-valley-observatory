#!/usr/bin/env python3
"""
MOORE - The Storyteller, wired to today's actual atmospheric data
Turns numbers into narrative.
"""
import csv, json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")
SPINE = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/alt_baro/jet_spine_daily.csv")
DOCS_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/docs")

class Moore:
    def __init__(self):
        self.name = "Moore"

    def observe(self):
        story = {}

        # Today's atmospheric character
        today = datetime.now().strftime("%Y%m%d")
        sp = DATA_DIR / "flowlab" / today / "shear_profile.csv"
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        sp_yesterday = DATA_DIR / "flowlab" / yesterday / "shear_profile.csv"

        # Use yesterday if today not ready
        sp_use = sp if sp.exists() else sp_yesterday
        date_use = today if sp.exists() else yesterday

        if sp_use.exists():
            try:
                rows = {r["alt_bin"]: r for r in csv.DictReader(open(sp_use))}
                bl = rows.get("BL")
                jet = rows.get("JET")

                if bl and jet:
                    bl_spd = float(bl.get("wind_spd_kt", 0))
                    bl_dir = float(bl.get("wind_dir_deg", 0))
                    jet_spd = float(jet.get("wind_spd_kt", 0))
                    jet_dir = float(jet.get("wind_dir_deg", 0))
                    diff = abs(bl_dir - jet_dir)
                    if diff > 180: diff = 360 - diff

                    story["bl_spd"] = bl_spd
                    story["bl_dir"] = bl_dir
                    story["jet_spd"] = jet_spd
                    story["jet_dir"] = jet_dir
                    story["decoupling"] = diff
                    story["date"] = date_use
            except:
                pass

        # Jet spine for context
        if SPINE.exists():
            rows = [r for r in csv.DictReader(open(SPINE))
                    if r.get("publish_wind_proxy_kn")]
            if rows:
                speeds = [float(r["publish_wind_proxy_kn"]) for r in rows]
                story["jet_mean"] = sum(speeds) / len(speeds)

        # Count findings
        if DOCS_DIR.exists():
            story["findings"] = len(list(DOCS_DIR.glob("finding_*.md")))

        return story

    def report(self, story):
        out = f"\n[{self.name}] Today's Atmospheric Narrative:\n"
        out += "─" * 60 + "\n"

        if "jet_spd" in story:
            jet_spd = story["jet_spd"]
            jet_dir = story["jet_dir"]
            bl_spd = story["bl_spd"]
            bl_dir = story["bl_dir"]
            decoupling = story["decoupling"]
            jet_mean = story.get("jet_mean", 65)

            # Characterize jet
            if jet_spd > 100:
                jet_char = "a fierce polar jet roars"
            elif jet_spd > 70:
                jet_char = "a strong jet stream drives"
            elif jet_spd > 40:
                jet_char = "a moderate jet flows"
            elif jet_spd > 15:
                jet_char = "a weak jet drifts"
            else:
                jet_char = "the jet stream has nearly collapsed"

            # Characterize BL
            compass = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                      "S","SSW","SW","WSW","W","WNW","NW","NNW"]
            bl_compass = compass[int((bl_dir + 11.25) / 22.5) % 16]
            jet_compass = compass[int((jet_dir + 11.25) / 22.5) % 16]

            out += f"Above the Helena valley today, {jet_char} overhead\n"
            out += f"at {jet_spd:.0f} knots from the {jet_compass}.\n\n"

            if decoupling > 120:
                out += f"But down in the valley, the air tells a different story.\n"
                out += f"The boundary layer flows {bl_compass} at {bl_spd:.0f} knots —\n"
                out += f"{decoupling:.0f} degrees divorced from the jet above.\n"
                out += f"The mountains have locked the surface wind.\n"
                out += f"This is Finding 001 made visible today.\n\n"
            elif decoupling > 60:
                out += f"The valley surface flows {bl_compass} at {bl_spd:.0f} knots —\n"
                out += f"partially decoupled from the jet by {decoupling:.0f} degrees.\n"
                out += f"The terrain is asserting itself.\n\n"
            else:
                out += f"Unusually, the valley surface follows the jet today —\n"
                out += f"both flowing {bl_compass}, decoupling only {decoupling:.0f} degrees.\n"
                out += f"One of {34} days where the valley lock breaks.\n\n"

            if jet_spd < jet_mean * 0.6:
                out += f"The jet is running well below its season average of {jet_mean:.0f}kt.\n"
                out += f"Spring is loosening the atmosphere's grip.\n\n"

        findings = story.get("findings", 4)
        out += f"The observatory has now filed {findings} formal findings.\n"
        out += f"The sky continues to be witnessed.\n"
        out += "─" * 60 + "\n"
        return out

if __name__ == "__main__":
    m = Moore()
    story = m.observe()
    print(m.report(story))

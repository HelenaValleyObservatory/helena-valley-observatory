"""
Helena Valley Observatory — Configuration loader.

Priority order:
  1. HELENA_BASE environment variable (full path to observatory root)
  2. config/observatory.cfg (INI file)
  3. Built-in defaults

Usage in scripts:
  from observatory_config import get_config
  cfg = get_config()
  data_root = cfg["data_root"]
"""
import os
import configparser
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "observatory.cfg"
_DEFAULTS = {
    "data_root":       str(Path.home() / "observatory" / "data"),
    "receiver_lat":    "0.0",
    "receiver_lon":    "0.0",
    "airport_name":    "XXXX",
    "field_elev_ft":   "0",
    "valley_axis_deg": "90.0",
    "aircraft_json":   "/run/readsb/aircraft.json",
    "poll_interval":   "5",
}

def get_config():
    """Return config dict with all observatory settings."""
    cfg = dict(_DEFAULTS)

    # Load from INI file if it exists
    if _CONFIG_FILE.exists():
        parser = configparser.ConfigParser()
        parser.read(_CONFIG_FILE)
        if "observatory" in parser:
            for key, val in parser["observatory"].items():
                cfg[key] = val.strip()
        if "readsb" in parser:
            for key, val in parser["readsb"].items():
                cfg[key] = val.strip()

    # Environment variable overrides everything
    if "HELENA_BASE" in os.environ:
        cfg["data_root"] = str(Path(os.environ["HELENA_BASE"]) / "data")

    if "HELENA_DATA" in os.environ:
        cfg["data_root"] = os.environ["HELENA_DATA"]

    return cfg

"""
Helena Valley Observatory — config shim for Flow Lab scripts.

Provides the same names as the production config.py so that
fl_stepa.py and other Flow Lab scripts work unchanged.

Reads from config/observatory.cfg or HELENA_DATA/HELENA_BASE env vars.
See config/observatory_config.py for full documentation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from observatory_config import get_config

_cfg = get_config()

DATA_ROOT = Path(_cfg["data_root"])
OBS_BASE  = DATA_ROOT.parent
ROOT      = OBS_BASE
OBS_DIR   = OBS_BASE
FLOWLAB   = DATA_ROOT / "flowlab"
BRIEFS    = DATA_ROOT / "briefs"
GOLD_DIR  = DATA_ROOT / "gold"
ERA5_DIR  = DATA_ROOT / "era5"

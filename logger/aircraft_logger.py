#!/usr/bin/env python3
"""
AIRCRAFT LOGGER v1.1 - Continuous ADS-B capture to JSONL
Reads from existing readsb, logs all aircraft observations
"""
import json
import time
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import configparser, os

def _load_config():
    cfg = configparser.ConfigParser()
    cfg_path = os.environ.get(
        "OBSERVATORY_CONFIG",
        os.path.join(os.path.dirname(__file__), "..", "config", "observatory.cfg")
    )
    cfg.read(cfg_path)
    return cfg

_cfg          = _load_config()
_root         = _cfg.get("observatory", "data_root", fallback="/tmp/observatory/data")
DATA_DIR      = Path(_root) / "aircraft"
JSON_FILE     = Path(_cfg.get("readsb", "aircraft_json",
                               fallback="/run/readsb/aircraft.json"))
POLL_INTERVAL = int(_cfg.get("readsb", "poll_interval", fallback="5"))

running = True

def shutdown(sig, frame):
    global running
    print("\n[aircraft_logger] Shutting down...")
    running = False

def get_output_file():
    """Daily rotation of output files"""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return DATA_DIR / f"aircraft_{day}.jsonl"

def parse_aircraft_json():
    """Read current aircraft from readsb JSON output"""
    if not JSON_FILE.exists():
        return []
    try:
        with open(JSON_FILE) as f:
            data = json.load(f)
        return data.get("aircraft", [])
    except (json.JSONDecodeError, IOError):
        return []

def log_aircraft(aircraft_list, outfile):
    """Log aircraft with timestamps"""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    logged = 0
    with open(outfile, "a") as f:
        for ac in aircraft_list:
            if not ac.get("hex"):
                continue
            
            record = {
                "timestamp": now,
                "hex": ac.get("hex", "").upper(),
                "flight": ac.get("flight", "").strip() if ac.get("flight") else None,
                "squawk": ac.get("squawk"),
                "lat": ac.get("lat"),
                "lon": ac.get("lon"),
                "alt_baro": ac.get("alt_baro"),
                "alt_geom": ac.get("alt_geom"),
                "gs": ac.get("gs"),
                "track": ac.get("track"),
                "baro_rate": ac.get("baro_rate"),
                "category": ac.get("category"),
                "nav_altitude_mcp": ac.get("nav_altitude_mcp"),
                "rssi": ac.get("rssi"),
                "messages": ac.get("messages"),
                "seen": ac.get("seen"),
                "distance_nm": ac.get("r_dst"),
                "bearing": ac.get("r_dir"),
            }
            
            # Remove None values to save space
            record = {k: v for k, v in record.items() if v is not None}
            
            f.write(json.dumps(record) + "\n")
            logged += 1
    
    return logged

def main():
    global running
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"[aircraft_logger] Starting v1.1 (read-only mode)")
    print(f"[aircraft_logger] Reading from: {JSON_FILE}")
    print(f"[aircraft_logger] Writing to: {DATA_DIR}/aircraft_YYYYMMDD.jsonl")
    print(f"[aircraft_logger] Poll interval: {POLL_INTERVAL}s")
    
    total_logged = 0
    last_day = None
    
    while running:
        try:
            current_day = datetime.now(timezone.utc).strftime("%Y%m%d")
            if current_day != last_day:
                print(f"[aircraft_logger] New day: {current_day}")
                last_day = current_day
            
            aircraft = parse_aircraft_json()
            if aircraft:
                outfile = get_output_file()
                logged = log_aircraft(aircraft, outfile)
                total_logged += logged
                if logged > 0:
                    print(f"[aircraft_logger] Logged {logged} aircraft (total: {total_logged})")
        
        except Exception as e:
            print(f"[aircraft_logger] Error: {e}")
        
        time.sleep(POLL_INTERVAL)
    
    print(f"[aircraft_logger] Stopped. Total logged: {total_logged}")

if __name__ == "__main__":
    main()

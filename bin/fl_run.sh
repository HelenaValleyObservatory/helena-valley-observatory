#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# OBSERVATORY FLOW LABORATORY — Pipeline Runner
# Runs the full 4-stage pipeline for a given date.
#
# Usage:
#   ./fl_run.sh YYYYMMDD
#   ./fl_run.sh --today
#   ./fl_run.sh --yesterday
#
# Stages:
#   1. fl_segment.py  — break JSONL into straight segments
#   2. fl_wind.py     — solve wind vectors per altitude/cell/time
#   3. fl_terrain.py  — channeling index + turbulence proxy
#   4. fl_report.py   — OFM-style text report
#
# Outputs land in:
#   $DATA_ROOT/flowlab/YYYYMMDD/
#   $DATA_ROOT/briefs/flowlab_YYYYMMDD.txt
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ── configuration ────────────────────────────────────────────────────────────
# Set OBSERVATORY_ROOT to your installation directory
# Or pass --root /your/path as first argument
if [[ "${1:-}" == "--root" ]]; then
  OBSERVATORY_ROOT="$2"; shift 2
else
  OBSERVATORY_ROOT="${OBSERVATORY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fi
BIN_DIR="${OBSERVATORY_ROOT}/bin"
DATA_ROOT="${OBSERVATORY_ROOT}/data"
export OBSERVATORY_CONFIG="${OBSERVATORY_ROOT}/config/observatory.cfg"

# ── argument parsing ──────────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 YYYYMMDD | --today | --yesterday"
    exit 1
fi

case "$1" in
    --today)
        DATE=$(date -u +%Y%m%d)
        ;;
    --yesterday)
        DATE=$(date -u -d "yesterday" +%Y%m%d)
        ;;
    *)
        DATE="$1"
        if ! [[ "$DATE" =~ ^[0-9]{8}$ ]]; then
            echo "[ERROR] Date must be YYYYMMDD, --today, or --yesterday"
            exit 1
        fi
        ;;
esac

DATE_FMT="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"
FLOWLAB_DIR="${DATA_ROOT}/flowlab/${DATE}"
JSONL="${DATA_ROOT}/aircraft/aircraft_${DATE}.jsonl"

echo "══════════════════════════════════════════════════════════════════════"
echo "  OBSERVATORY FLOW LABORATORY — ${DATE_FMT}"
echo "══════════════════════════════════════════════════════════════════════"
echo "  Date       : ${DATE_FMT}"
echo "  JSONL      : ${JSONL}"
echo "  Output dir : ${FLOWLAB_DIR}"
echo "  Scripts    : ${BIN_DIR}"
echo "══════════════════════════════════════════════════════════════════════"
echo ""

# ── preflight checks ──────────────────────────────────────────────────────────
echo "[ pre-flight ]"

if [[ ! -f "$JSONL" ]]; then
    echo "  [ERROR] JSONL not found: $JSONL"
    exit 1
fi

LINES=$(wc -l < "$JSONL")
echo "  JSONL exists: $LINES lines"

for script in fl_segment.py fl_wind.py fl_terrain.py fl_report.py; do
    if [[ ! -f "${BIN_DIR}/${script}" ]]; then
        echo "  [ERROR] Script missing: ${BIN_DIR}/${script}"
        exit 1
    fi
done

for f in channeling_map.parquet turbulence_map.parquet; do
path="${FLOWLAB_DIR}/${f}"
if [[ -f "$path" ]]; then
  SIZE=$(du -h "$path" | cut -f1)
  echo "  ✓ ${f}  (${SIZE})"
else
  echo "  ~ ${f}  (not produced — insufficient low-altitude data)"
fi
done
echo "  All scripts present."
echo ""

mkdir -p "$FLOWLAB_DIR"

# ── stage 1: segmentation ─────────────────────────────────────────────────────
echo "[ stage 1/4 ] Segmenter"
echo "──────────────────────────────────────────────────────────────────────"
python "${BIN_DIR}/fl_segment.py" --date "${DATE}"
echo ""

# ── stage 2: wind solver ──────────────────────────────────────────────────────
echo "[ stage 2/4 ] Wind Solver"
echo "──────────────────────────────────────────────────────────────────────"
python "${BIN_DIR}/fl_wind.py" --date "${DATE}"
echo ""

# ── stage 3: terrain + turbulence ─────────────────────────────────────────────
echo "[ stage 3/4 ] Terrain Channeling + Turbulence Proxy"
echo "──────────────────────────────────────────────────────────────────────"
python "${BIN_DIR}/fl_terrain.py" --date "${DATE}"
echo ""

# ── stage 4: report ───────────────────────────────────────────────────────────
echo "[ stage 4/4 ] Daily Lab Report"
echo "──────────────────────────────────────────────────────────────────────"
python "${BIN_DIR}/fl_report.py" --date "${DATE}"
echo ""

# ── verification ──────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo "  VERIFICATION"
echo "══════════════════════════════════════════════════════════════════════"
echo ""

for f in segments.csv wind_cells.csv shear_profile.csv; do
    path="${FLOWLAB_DIR}/${f}"
    if [[ -f "$path" ]]; then
        SIZE=$(du -h "$path" | cut -f1)
        echo "  ✓ ${f}  (${SIZE})"
    else
        echo "  ✗ MISSING: ${f}"
    fi
done

BRIEF="${DATA_ROOT}/briefs/flowlab_${DATE}.txt"
if [[ -f "$BRIEF" ]]; then
    echo "  ✓ flowlab_${DATE}.txt  ($(du -h "$BRIEF" | cut -f1))"
else
    echo "  ✗ MISSING: brief"
fi

echo ""
echo "  Pipeline complete for ${DATE_FMT}."
echo "  Brief: ${BRIEF}"
echo ""
echo "  To view: cat ${BRIEF}"
echo "══════════════════════════════════════════════════════════════════════"

# EpochZero Phase 1.2 v0.9.2

## Epistemic Hypothesis Generator

> ⚠️ **NOT a causal engine. NOT a discovery engine.**
>
> **This is an EPISTEMIC HYPOTHESIS GENERATOR.**
>
> **Produces HYPOTHESES only — temporal precedence, NOT causation.**

---

## v0.9.2: Null-Calibrated Event-Triggered Falsification

### The Problem (Measured in Calibration)

| Metric | Old (d≥0.3) | New (null-calibrated) |
|--------|-------------|----------------------|
| TRUE detection | 96% | 45% |
| NULL detection (FP) | 43% | 10% |
| Precision | 69% | 82% |

**Root cause**: Event-triggered analysis produced substantial effect sizes even for NULL relationships due to random event-numeric alignment.

### The Solution

**Null-calibrated significance testing**:
1. Compute observed effect size
2. Generate null distribution via **circular shift** (50 trials)
3. Require `effect_size > p95_null`
4. Verify **lag stability** via bootstrap resampling

```
effect_size: 0.723
p95_null:    0.641
margin:      +0.082  ← PASSES NULL TEST
lag_stable:  true    ← 73% agreement on lag=2
```

### What Changed

| Component | Old | New |
|-----------|-----|-----|
| Threshold | Fixed d≥0.3 | Null-calibrated p95 |
| Falsification | None | Circular shift + bootstrap |
| FP rate | ~43% | ~10% |
| Recovery | ~96% | ~45% |

**Tradeoff accepted**: Lower recovery for higher precision.

---

## Invariants Preserved

- ✓ min_events=8 LOCKED
- ✓ No threshold tuning (null distribution is computed, not chosen)
- ✓ No fabrication
- ✓ No quota forcing
- ✓ All hypotheses require falsification

---

## Event-Triggered Falsification Pipeline

```
Event-Numeric Pair
        ↓
┌───────────────────────────────┐
│ 1. Compute effect_size_d      │
│    (pre/post window delta)    │
└───────────────────────────────┘
        ↓
┌───────────────────────────────┐
│ 2. Generate null distribution │
│    (50× circular shift)       │
│    → compute p95_null         │
└───────────────────────────────┘
        ↓
┌───────────────────────────────┐
│ 3. NULL TEST                  │
│    effect_size > p95_null?    │
│    FAIL → reject hypothesis   │
└───────────────────────────────┘
        ↓
┌───────────────────────────────┐
│ 4. BOOTSTRAP LAG STABILITY    │
│    20× resample events        │
│    >60% agreement on lag?     │
│    FAIL → reject hypothesis   │
└───────────────────────────────┘
        ↓
    PASSES FALSIFICATION
```

---

## Hypothesis Output (Event-Triggered)

```json
{
  "method": "event_triggered",
  "event_key": "usb_snapshot",
  "numeric_key": "temp_Tctl",
  "effect_size_d": 0.723,
  "null_distribution": {
    "null_trials": 50,
    "null_mean": 0.312,
    "p95_null": 0.641
  },
  "significance_margin": 0.082,
  "passes_null_test": true,
  "lag_stability": {
    "stable": true,
    "agreement_rate": 0.73,
    "original_lag": 2
  },
  "passes_falsification": true,
  "tag": "Derived/Falsified"
}
```

---

## Calibration Results (from Synthetic Harness)

| Density | Gate | Old FP | New FP | Status |
|---------|------|--------|--------|--------|
| 5 | BLOCKED | — | — | min_events gate ✓ |
| 6 | BLOCKED | — | — | min_events gate ✓ |
| 7 | BLOCKED | — | — | min_events gate ✓ |
| 8 | PASSED | 87% | ~10% | NULL-calibrated ✓ |
| 15 | PASSED | 85% | ~10% | NULL-calibrated ✓ |
| 30 | PASSED | 82% | ~10% | NULL-calibrated ✓ |

---

## CLI Reference

```bash
# Full pipeline
epochzero run --duration 180 --mode stimulated

# Aggregation (N≥3 required)
epochzero aggregate --last 3

# Status
epochzero status
```

---

## Hard Invariants

| Invariant | v0.9.2 Status |
|-----------|---------------|
| min_events=8 LOCKED | ✓ |
| Null-calibrated falsification | ✓ NEW |
| Lag stability check | ✓ NEW |
| No threshold tuning | ✓ |
| No fabrication | ✓ |
| No quota forcing | ✓ |

---

## Version

EpochZero Phase 1.2 v0.9.2

**FP target: ≤20% — ACHIEVED: ~10%**

---

**This is an EPISTEMIC INSTRUMENT.**

**Zero hypotheses = epistemically correct.**

**Convincing nonsense is worse than no output.**

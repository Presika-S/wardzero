"""Safety-floor bands and data-quality checks.

The bands follow the published NEWS2 structure for the four parameters we simulate
(SpO2 scale 1, systolic BP, pulse, temperature). Respiratory rate, consciousness and
supplemental oxygen are NOT simulated, so this is a *partial, illustrative* score.
It is a safety floor for a prototype - not a clinical tool.
"""
import math

LIMITS = {"temp": (30.0, 43.0), "hr": (20, 250), "sbp": (50, 260), "dbp": (20, 160), "spo2": (50, 100)}
VITALS = ("temp", "hr", "sbp", "spo2")
LABEL = {"temp": "Temperature", "hr": "Heart rate", "sbp": "Systolic BP", "dbp": "Diastolic BP", "spo2": "SpO2"}
UNIT = {"temp": "°C", "hr": "bpm", "sbp": "mmHg", "dbp": "mmHg", "spo2": "%"}


def score_spo2(v):
    return 3 if v <= 91 else 2 if v <= 93 else 1 if v <= 95 else 0

def score_sbp(v):
    return 3 if v <= 90 else 2 if v <= 100 else 1 if v <= 110 else 3 if v >= 220 else 0

def score_hr(v):
    return 3 if v <= 40 else 1 if v <= 50 else 0 if v <= 90 else 1 if v <= 110 else 2 if v <= 130 else 3

def score_temp(v):
    return 3 if v <= 35.0 else 1 if v <= 36.0 else 0 if v <= 38.0 else 1 if v <= 39.0 else 2

_SCORERS = {"spo2": score_spo2, "sbp": score_sbp, "hr": score_hr, "temp": score_temp}


def news2(r):
    """Partial NEWS2-style score. Returns {subs, total, red}. Any single sub-score of 3 is 'red'."""
    subs = {k: _SCORERS[k](r[k]) for k in VITALS}
    return {"subs": subs, "total": sum(subs.values()), "red": [k for k, s in subs.items() if s == 3]}


def invalid_reason(r):
    """Physiologically impossible / missing values => sensor fault, never a clinical alarm."""
    for k, (lo, hi) in LIMITS.items():
        v = r.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return f"{LABEL[k]} missing"
        if not lo <= v <= hi:
            return f"{LABEL[k]} reads {v:g}, outside the physically possible range"
    if r["dbp"] >= r["sbp"]:
        return "Diastolic pressure is not below systolic"
    if r.get("quality", 1.0) < 0.5:
        return f"Device-reported signal quality is low ({r.get('quality'):.2f})"
    return None


def is_flatline(recent, n=6):
    """True if the last n raw readings are identical across all vitals (frozen sensor)."""
    if len(recent) < n:
        return False
    last = recent[-n:]
    key = ("temp", "hr", "sbp", "dbp", "spo2")
    return all(tuple(x[k] for k in key) == tuple(last[0][k] for k in key) for x in last)

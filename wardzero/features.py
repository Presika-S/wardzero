"""Rolling-window features + plain-language explanations.

Window: 24 readings = 6 sim-hours (short), 48 readings = 12 sim-hours (long); 1 reading = 15 sim-minutes.
Per vital: slope/h (6h), delta vs the patient's OWN baseline (6h mean), residual variability (6h),
and fraction of the last 12h beyond a soft threshold ("time above/below threshold").
"""
import numpy as np
from .physio import news2, LABEL

W6, W12 = 24, 48
VIT = ("temp", "hr", "sbp", "spo2")
THR = {"temp": (">", 37.6), "hr": (">", 95.0), "sbp": ("<", 108.0), "spo2": ("<", 95.0)}
MIN_SD = {"temp": 0.10, "hr": 2.0, "sbp": 3.0, "spo2": 0.4}
FEATURE_NAMES = [f"{v}_{s}" for v in VIT for s in ("slope6", "delta6", "std6", "frac12")] + ["news2_now", "news2_max6"]

_X = (np.arange(W6) - (W6 - 1) / 2) * 0.25
_XX = float((_X ** 2).sum())


def calibrate(h, n):
    """Personal baseline = robust median and MAD-sd of the first n (stable) readings."""
    out = {}
    for v in VIT:
        a = np.asarray(h[v][:n], dtype=float)
        med = float(np.median(a))
        sd = float(np.median(np.abs(a - med))) * 1.4826
        out[v] = (med, max(sd, MIN_SD[v]))
    return out


def extract(h, base):
    """h: dict vital -> chronological np.array (>= 48 long). Returns (vector, raw) or None."""
    if len(h["hr"]) < W12:
        return None
    f, raw = [], {}
    for v in VIT:
        a = np.asarray(h[v][-W12:], dtype=float)
        a6 = a[-W6:]
        slope = float((_X * (a6 - a6.mean())).sum() / _XX)
        std = float((a6 - (a6.mean() + slope * _X)).std())
        delta = float(a6.mean() - base[v][0])
        op, t = THR[v]
        frac = float(((a > t) if op == ">" else (a < t)).mean())
        f += [slope, delta, std, frac]
        raw[v] = dict(slope=slope, delta=delta, std=std, frac=frac, base=base[v][0], sd=base[v][1])
    n = len(h["hr"])
    tots = [news2({k: float(h[k][n - W6 + i]) for k in VIT})["total"] for i in range(W6)]
    f += [float(tots[-1]), float(max(tots))]
    raw["news2_now"], raw["news2_max6"] = tots[-1], max(tots)
    return np.array(f, dtype=float), raw


def describe(name, raw):
    """Turn one model feature into a short human sentence."""
    if name.startswith("news2"):
        return (f"Early-warning score is {raw['news2_now']} now (illustrative NEWS2-style)" if name == "news2_now"
                else f"Early-warning score peaked at {raw['news2_max6']} in the last 6h")
    v, kind = name.rsplit("_", 1)
    r, lab = raw[v], LABEL[v]
    if kind == "delta6":
        unit = {"temp": "°C", "hr": " bpm", "sbp": " mmHg", "spo2": " points"}[v]
        fmt = "{:+.1f}" if v in ("temp", "spo2") else "{:+.0f}"
        return f"{lab} {fmt.format(r['delta'])}{unit} vs the patient's own baseline (6h average)"
    if kind == "slope6":
        unit = {"temp": "°C/h", "hr": "bpm/h", "sbp": "mmHg/h", "spo2": "pts/h"}[v]
        word = "rising" if r["slope"] > 0 else "falling"
        return f"{lab} {word} ~{abs(r['slope']):.2f} {unit}" if v == "temp" else f"{lab} {word} ~{abs(r['slope']):.1f} {unit}"
    if kind == "std6":
        return f"{lab} unusually variable over 6h"
    op, t = THR[v]
    return f"{lab} {'above' if op == '>' else 'below'} {t:g} for {r['frac'] * 100:.0f}% of the last 12h"

"""Train the 24-48h deterioration-risk model on SYNTHETIC episodes.

Label = 1 for windows that fall 'within 48h before a simulated deterioration event' (and after the drift has
started to show). Hard negatives: stable patients, transient fevers that resolve, and patients whose personal
normal is unusual (low SpO2 / high HR) - the cases a fixed threshold gets wrong.

HONESTY NOTE: labels come from our own simulator, so the metrics prove the pipeline and its explainability,
not clinical accuracy. Run:  python -m wardzero.train
"""
import json, time
from datetime import datetime, timezone
import joblib, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from . import config
from .features import FEATURE_NAMES, VIT, calibrate, extract, W12
from .synth import PatientSim, BASE

CAL = config.CALIB_N


def make_episode(rng, kind):
    base = dict(BASE)
    base["temp"] += rng.normal(0, 0.2); base["hr"] += rng.normal(0, 8); base["sbp"] += rng.normal(0, 8)
    base["spo2"] = float(np.clip(rng.normal(97, 1.0), 94, 99))
    if kind == "chronic":                       # personally-normal low SpO2 / high HR: fixed thresholds misfire
        base["spo2"], base["hr"] = rng.uniform(92.5, 94.5), base["hr"] + 10
    sev, D, T = rng.uniform(0.5, 1.25), int(rng.integers(120, 185)), CAL + 300
    te = int(rng.integers(CAL + D + 10, T)) if kind == "det" else None
    t0 = te - D if te else None
    tr = (int(rng.integers(CAL + 20, T - 40)), int(rng.integers(16, 36))) if kind == "transient" else None
    sim = PatientSim(seed=int(rng.integers(1 << 30)), base=base, severity=sev, drift_hours=D * 0.25, noise_scale=float(rng.uniform(1.0, 2.6)),
                     start=datetime(2026, 1, 1, int(rng.integers(0, 24))))
    rows, end = [], (te if te else T)
    for i in range(end + 1):
        if kind == "det":
            mode = "slow_deterioration" if i >= t0 else "stable"
        elif tr and tr[0] <= i < tr[0] + tr[1]:
            mode = "transient"
        else:
            mode = "stable"
        rows.append(sim.step(mode))
    h = {v: np.array([r[v] for r in rows]) for v in VIT}
    return h, t0, te


def windows(h, t0, te, every=3):
    base = calibrate(h, CAL)
    X, y, idx = [], [], []
    for i in range(CAL, len(h["hr"]), every):
        sub = {v: h[v][:i + 1] for v in VIT}
        out = extract(sub, base)
        if out is None: continue
        X.append(out[0]); idx.append(i)
        y.append(int(te is not None and i >= t0 + 12 and i >= te - 192 and i <= te))
    return np.array(X), np.array(y), idx


def main(n_episodes=320, seed=7):
    t_start = time.time()
    rng = np.random.default_rng(seed)
    kinds = rng.choice(["stable", "transient", "chronic", "det"], size=n_episodes, p=[0.3, 0.2, 0.1, 0.4])
    eps = [make_episode(rng, k) + (k,) for k in kinds]
    cut = int(n_episodes * 0.8)
    Xtr, ytr = [], []
    for h, t0, te, k in eps[:cut]:
        X, y, _ = windows(h, t0, te)
        Xtr.append(X); ytr.append(y)
    Xtr, ytr = np.vstack(Xtr), np.concatenate(ytr)
    pipe = Pipeline([("sc", StandardScaler()), ("lr", LogisticRegression(C=0.3, max_iter=3000, class_weight={0: 1, 1: 1.2}))])
    pipe.fit(Xtr, ytr)

    # ---- held-out evaluation (per tick so we can measure persistence + lead time)
    ys, ps, lead, det_n, fa, neg_n = [], [], [], 0, 0, 0
    for h, t0, te, k in eps[cut:]:
        X, y, idx = windows(h, t0, te, every=1)
        p = pipe.predict_proba(X)[:, 1]
        ys.append(y); ps.append(p)
        run, first = 0, None
        for j, pj in zip(idx, p):
            run = run + 1 if pj >= config.BAND_MEDIUM else 0
            if run >= config.PERSIST_RISK and first is None: first = j
        if k == "det":
            det_n += 1
            if first is not None and first <= te: lead.append((te - first) * 0.25)
        else:
            neg_n += 1; fa += first is not None
    ys, ps = np.concatenate(ys), np.concatenate(ps)
    card = {
        "model": "StandardScaler + LogisticRegression (interpretable; contributions are exact)",
        "trained_on": f"{cut} synthetic episodes; evaluated on {n_episodes - cut} held-out synthetic episodes",
        "features": FEATURE_NAMES,
        "coefficients": {n: round(float(c), 3) for n, c in zip(FEATURE_NAMES, pipe.named_steps['lr'].coef_[0])},
        "bands": {"medium": config.BAND_MEDIUM, "high": config.BAND_HIGH},
        "metrics_synthetic": {
            "auroc": round(float(roc_auc_score(ys, ps)), 3),
            "episodes_with_early_warning": f"{len(lead)}/{det_n}",
            "median_lead_time_hours_before_event": round(float(np.median(lead)), 1) if lead else None,
            "episodes_without_deterioration_that_still_raised_alert": f"{fa}/{neg_n}",
            "persistence_rule": f"{config.PERSIST_RISK} consecutive readings at Medium or above",
        },
        "limitations": [
            "Labels come from our own simulator: metrics show the pipeline works, NOT clinical accuracy.",
            "Partial NEWS2-style inputs only (no respiratory rate, consciousness, oxygen).",
            "Not validated on any real patient data. Not a medical device. No diagnosis is made.",
        ],
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "seconds": round(time.time() - t_start, 1),
    }
    import os
    os.makedirs(os.path.dirname(config.MODEL_PATH) or ".", exist_ok=True)
    joblib.dump({"pipe": pipe, "names": FEATURE_NAMES, "card": card}, config.MODEL_PATH)
    json.dump(card, open(os.path.join(os.path.dirname(config.MODEL_PATH) or ".", "model_card.json"), "w"), indent=2)
    print(json.dumps(card["metrics_synthetic"], indent=2), f"\n{card['seconds']}s")
    return card


if __name__ == "__main__":
    main()

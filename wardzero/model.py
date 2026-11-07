"""Interpretable risk model wrapper: logistic regression + per-feature contributions."""
import joblib
import numpy as np
from . import config
from .features import describe, FEATURE_NAMES


def band(p):
    return "High" if p >= config.BAND_HIGH else "Medium" if p >= config.BAND_MEDIUM else "Low"


class RiskModel:
    def __init__(self, path):
        d = joblib.load(path)
        self.pipe, self.names, self.card = d["pipe"], d["names"], d["card"]
        self.sc, self.lr = self.pipe.named_steps["sc"], self.pipe.named_steps["lr"]

    def predict(self, x, raw, nudge=0.0):
        """Exact additive explanation: logit = intercept + sum(coef_i * z_i) (+ caregiver-note nudge)."""
        z = (x - self.sc.mean_) / self.sc.scale_
        contrib = self.lr.coef_[0] * z
        logit = float(contrib.sum() + self.lr.intercept_[0] + nudge)
        p = float(1 / (1 + np.exp(-logit)))
        order = np.argsort(-contrib)
        top = [{"feature": self.names[i], "contribution": round(float(contrib[i]), 3),
                "text": describe(self.names[i], raw)} for i in order if contrib[i] > 0.2 and not self.names[i].endswith("std6")
               and not (self.names[i].endswith("frac12") and raw[self.names[i].split("_")[0]]["frac"] < 0.05)][:4]
        return {"prob": round(p, 3), "band": band(p), "top": top, "nudge": nudge}

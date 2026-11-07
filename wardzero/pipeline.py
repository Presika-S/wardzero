"""Glue: reading -> engine -> alarm-fatigue rules (persistence, dedupe, cooldown, quality gating) -> alerts."""
from . import config
from .physio import LABEL, UNIT, news2


def fmt(k, v):
    return f"{v:g}{UNIT[k]}" if UNIT[k] in ("%", "°C") else f"{v:g} {UNIT[k]}"

RED_TEXT = {"spo2": "≤91 %", "sbp": "≤90 or ≥220 mmHg", "hr": "≤40 or ≥131 bpm", "temp": "≤35.0 °C"}


class Pipeline:
    def __init__(self, engine, alerts):
        self.engine, self.alerts = engine, alerts
        self.reset()

    def reset(self):
        self.engine.reset()
        self.streak, self.miss, self.last_risk, self.last_news2 = {}, {}, None, None

    def _cond(self, key, hit, need, fire, now=None):
        L = self.alerts.ledger
        if hit:
            self.streak[key] = self.streak.get(key, 0) + 1
            self.miss[key] = 0
            if self.streak[key] >= need:
                fire()
            else:
                L["persistence"] += 1
        else:
            self.streak[key] = 0
            self.miss[key] = self.miss.get(key, 0) + 1
            if self.miss[key] == config.CLEAR_AFTER:
                self.alerts.clear(key, now=now)

    def process(self, r, seed=False, now=None):
        res = self.engine.process(r)
        if res["valid"]:
            self.last_risk, self.last_news2 = res.get("risk"), res["news2"]
        if seed:
            return res
        A, L, ts = self.alerts, self.alerts.ledger, r["ts"]
        # what a naive fixed-threshold monitor would have alarmed on (for the Suppression Ledger)
        n2 = news2(r) if res["valid"] else None
        if (not res["valid"]) or n2["total"] >= 1:
            L["raw_hits"] += 1

        # ---- device / equipment health (never clinical)
        self._cond("device:battery", r.get("battery", 100) < 20, 1, lambda: A.trigger(
            "device:battery", "DEVICE", "Info", "Bedside device battery low",
            [f"Battery at {r.get('battery'):.0f}% — replace or recharge"], ts, now), now)
        self._cond("device:power", r.get("power") == "battery", 1, lambda: A.trigger(
            "device:power", "DEVICE", "Info", "Mains power lost — device running on battery",
            ["Monitoring continues on battery; check the power supply"], ts, now), now)

        # ---- signal-quality gate: bad data can NEVER raise a clinical alarm
        if not res["valid"]:
            L["gated_quality"] += 1
            self._cond("device:fault", True, 3, lambda: A.trigger(
                "device:fault", "SENSOR_FAULT", "Info", "Sensor signal unreliable — check probe / cable",
                [res["fault"], "Readings are excluded from risk assessment until the signal recovers"], ts, now), now)
            return res
        self._cond("device:fault", False, 1, lambda: None, now)

        # ---- 1. rule-based safety floor (always on)
        red = n2["red"]
        crit = bool(red) or n2["total"] >= 7
        reasons = [f"{LABEL[k]} {fmt(k, r[k])} — red band ({RED_TEXT[k]}; illustrative)" for k in red]
        if not red and n2["total"] >= 7:
            reasons = [f"Early-warning score {n2['total']} (≥7; illustrative NEWS2-style)"]
        if res["risk"]:
            reasons.append(f"24–48h risk outlook: {res['risk']['band']} ({res['risk']['prob']:.0%})")
        self._cond("floor:red", crit, config.PERSIST_CRITICAL, lambda: A.trigger(
            "floor:red", "FLOOR", "Critical", "Critical vital signs — act now", reasons, ts, now), now)
        self._cond("floor:agg", (not crit) and n2["total"] >= 5, config.PERSIST_WARNING, lambda: A.trigger(
            "floor:agg", "FLOOR", "Warning", "Early-warning score elevated",
            [f"Score {n2['total']} (≥5; illustrative NEWS2-style)"], ts, now), now)

        # ---- 2. personal baseline + trend model (24-48h outlook)
        rk = res["risk"]
        if rk:
            why = [t["text"] for t in rk["top"][:3]] + [f"Caregiver note: {x}" for x in rk["notes"]]
            title = ("High" if rk["band"] == "High" else "Rising") + " deterioration risk (24–48h outlook)"
            self._cond("risk:elevated", rk["band"] != "Low", config.PERSIST_RISK, lambda: A.trigger(
                "risk:elevated", "RISK", "Warning", title,
                why + [f"Model probability {rk['prob']:.0%} — experimental, synthetic-data model"], ts, now), now)
        return res

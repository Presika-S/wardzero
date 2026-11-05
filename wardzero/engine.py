"""Per-patient risk engine: quality gate -> safety floor -> personal baseline -> trend model -> caregiver-note nudge."""
from datetime import datetime
import numpy as np
from . import config, notes as notes_mod
from .features import VIT, W12, calibrate, extract
from .model import RiskModel
from .physio import news2, invalid_reason, is_flatline

NOTE_WINDOW_S = 12 * 3600          # a caregiver note influences risk for 12 simulated hours


class Engine:
    def __init__(self, model: RiskModel):
        self.model = model
        self.reset()

    def reset(self):
        self.raw, self.ts, self.base, self.notes = [], [], None, []
        self.h = {v: [] for v in VIT}

    def add_note(self, sim_ts, analysis, text):
        self.notes.append((datetime.fromisoformat(sim_ts), analysis, text))

    def _active_notes(self, t):
        act = [(a, tx) for (nt, a, tx) in self.notes if 0 <= (t - nt).total_seconds() <= NOTE_WINDOW_S]
        flags = {}
        for a, _ in act:
            for f, lab in zip(a["flags"], a["labels"]):
                flags[f] = lab
        nudge = min(notes_mod.MAX_NUDGE, sum(notes_mod.FLAGS[f][0] for f in flags))
        return list(flags.values()), nudge

    def baseline_summary(self):
        return {v: {"median": round(m, 2), "sd": round(sd, 2)} for v, (m, sd) in (self.base or {}).items()}

    def process(self, r):
        t = datetime.fromisoformat(r["ts"])
        self.raw = (self.raw + [r])[-8:]
        bad = invalid_reason(r)
        if bad is None and is_flatline(self.raw):
            bad = "Sensor output frozen (identical values for 6 readings)"
        if bad:
            return {"valid": False, "fault": bad}
        for v in VIT:
            self.h[v].append(float(r[v]))
        if self.base is None and len(self.h["hr"]) >= config.CALIB_N:
            self.base = calibrate(self.h, config.CALIB_N)
        elif self.base is not None and len(self.h["hr"]) > 600:
            for v in VIT:
                self.h[v] = self.h[v][-400:]
        out = {"valid": True, "fault": None, "news2": news2(r), "risk": None, "baseline": self.baseline_summary()}
        if self.base is not None:
            ex = extract({v: np.array(self.h[v][-W12:]) for v in VIT}, self.base)
            if ex is not None:
                labels, nudge = self._active_notes(t)
                risk = self.model.predict(ex[0], ex[1], nudge)
                risk["notes"] = labels
                risk["raw"] = {v: {"delta": round(ex[1][v]["delta"], 2), "slope": round(ex[1][v]["slope"], 3)} for v in VIT}
                out["risk"] = risk
        return out

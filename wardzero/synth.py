"""Synthetic physiology generator. Used by BOTH the device simulator and the ML trainer,
so the demo and the training data come from the same (documented) process.
All numbers are invented for a software prototype; nothing here is real patient data."""
import math
from datetime import datetime, timedelta
import numpy as np

BASE = dict(temp=36.7, hr=74.0, sbp=122.0, dbp=78.0, spo2=97.0)
SIGMA = np.array([0.07, 2.2, 2.8, 1.8, 0.45])      # temp, hr, sbp, dbp, spo2 (AR(1) noise)
KEYS = ("temp", "hr", "sbp", "dbp", "spo2")
# Total change reached by the end of a deterioration run (scaled by severity)
MAG = dict(temp=2.1, hr=45.0, sbp=-33.0, dbp=-18.0, spo2=-6.2)
ACUTE = dict(temp=1.4, hr=60.0, sbp=-45.0, dbp=-25.0, spo2=-10.0)
TRANSIENT = dict(temp=1.0, hr=14.0, sbp=0.0, dbp=0.0, spo2=0.0)


class PatientSim:
    def __init__(self, seed=0, base=None, start=None, tick_min=15, severity=1.0, drift_hours=30.0, noise_scale=1.0):
        self.rng = np.random.default_rng(seed)
        self.base = dict(base or BASE)
        self.off = {k: 0.0 for k in KEYS}
        self.noise = np.zeros(5)
        self.t = start or datetime(2026, 11, 3, 6, 0, 0)
        self.dt_h = tick_min / 60.0
        self.tick_min = tick_min
        self.severity, self.drift_hours, self.noise_scale = severity, drift_hours, noise_scale
        self.battery, self.seq, self.last = 100.0, 0, None

    def _circ(self):
        h = self.t.hour + self.t.minute / 60
        s = lambda ph: math.sin(2 * math.pi * (h - ph) / 24)
        return dict(temp=0.25 * s(11.5), hr=3.5 * s(9), sbp=4.0 * s(9), dbp=2.0 * s(9), spo2=0.0)

    def _update_offsets(self, mode):
        if mode == "slow_deterioration":
            for k in KEYS:
                self.off[k] += MAG[k] * self.severity / self.drift_hours * self.dt_h
        elif mode in ("acute_event", "transient"):
            tgt = ACUTE if mode == "acute_event" else TRANSIENT
            for k in KEYS:
                goal = tgt[k] * (self.severity if mode == "transient" else 1.0)
                if abs(goal) > abs(self.off[k]) or goal * self.off[k] < 0:
                    self.off[k] += 0.4 * (goal - self.off[k])
        else:  # stable / recovering
            for k in KEYS:
                self.off[k] *= 0.88

    def step(self, mode="stable", fault=None, power_loss=False, device_id="bedside-01"):
        self._update_offsets(mode)
        self.noise = 0.6 * self.noise + SIGMA * self.noise_scale * self.rng.standard_normal(5)
        c = self._circ()
        v = {k: self.base[k] + c[k] + self.off[k] + self.noise[i] for i, k in enumerate(KEYS)}
        v["spo2"] = min(100.0, v["spo2"])
        r = {k: round(float(v[k]), 2 if k == "temp" else 1) for k in KEYS}
        quality = 0.95
        if fault == "probe_off":
            r["spo2"], r["hr"], quality = 0.0, 0.0, 0.15
        elif fault == "flatline" and self.last:
            r = {k: self.last[k] for k in KEYS}
        else:
            self.last = dict(r)
        self.battery = max(0.0, self.battery - (0.35 if power_loss else 0.02))
        self.seq += 1
        out = {"device_id": device_id, "seq": self.seq, "ts": self.t.isoformat(), **r,
               "quality": quality, "battery": round(self.battery, 1),
               "power": "battery" if power_loss else "mains"}
        self.t += timedelta(minutes=self.tick_min)
        return out

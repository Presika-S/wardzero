"""Core application object (framework-free so it can be unit-tested): ingestion, control, heartbeat, state."""
import asyncio, json, os, time
from datetime import datetime
from . import config, notes as notes_mod
from .alerts import AlertManager
from .audit import AuditLog
from .db import Audit, Base, Note, Reading, make_session_factory
from .engine import Engine
from .model import RiskModel
from .notifier import MockNotifier, NtfyNotifier
from .pipeline import Pipeline

REQUIRED = ("device_id", "ts", "temp", "hr", "sbp", "dbp", "spo2")


class StaleEpoch(Exception):
    pass


class Hub:
    """Fan-out to WebSocket clients through per-client queues (ordered, never blocks the pipeline)."""
    def __init__(self):
        self.queues = set()

    def emit(self, msg):
        data = json.dumps(msg, default=str)
        for q in list(self.queues):
            if q.qsize() > 2000:
                self.queues.discard(q)           # drop a hopelessly slow client
            else:
                q.put_nowait(data)


class Core:
    def __init__(self, db_url=None, model_path=None):
        self.engine_db, self.S = make_session_factory(db_url or config.DB_URL)
        self.hub = Hub()
        path = model_path or config.MODEL_PATH
        if not os.path.exists(path):
            from . import train
            config.MODEL_PATH = path
            train.main()
        self.model = RiskModel(path)
        self.audit = AuditLog(self.S)
        notifiers = [MockNotifier(self.hub.emit)] + ([NtfyNotifier(config.NTFY_URL)] if config.NTFY_URL else [])
        self.alerts = AlertManager(self.S, self.audit, self.hub.emit, notifiers)
        self.pipeline = Pipeline(Engine(self.model), self.alerts)
        self.control = {"physio": "stable", "fault": None, "link_up": True, "power_loss": False, "speed": 4, "epoch": 1}
        self.last_rx = None; self.last_sim_ts = None; self.last_reading = None
        self.nodata = False; self.replay_until = 0.0; self.last_replay = None
        self.checkins = {}
        self.judge = None
        self._restore()
        self.audit.append("system", "system_started", detail={"note": "experimental prototype, synthetic data"})

    def _restore(self):
        """Crash recovery: rebuild the in-memory engine (baseline, history, notes, epoch) from the database so a
        server restart does not silently lose the patient's learned baseline. Open alerts live in the DB already."""
        with self.S() as s:
            lr = s.query(Audit).filter(Audit.action == "reset").order_by(Audit.id.desc()).first()
            rows = s.query(Reading).order_by(Reading.id).limit(5000).all()
            notes = s.query(Note).order_by(Note.id).all()
        if lr:
            self.control["epoch"] = json.loads(lr.detail).get("epoch", 1)
        last = None
        for r in rows:
            d = {k: getattr(r, k) for k in ("device_id", "seq", "ts", "temp", "hr", "sbp", "dbp", "spo2", "quality", "battery", "power")}
            last = (d, self.pipeline.engine.process(d))
        for n in notes:
            self.pipeline.engine.add_note(n.sim_ts, notes_mod.analyze(n.text), n.text)
        if last:
            self.last_sim_ts, self.last_reading = last[0]["ts"], self.reading_msg(*last)
            self.pipeline.last_risk = last[1].get("risk")

    # ------------------------------------------------------------ control plane
    def set_control(self, **kw):
        ch = {k: v for k, v in kw.items() if k in self.control and k != "epoch" and self.control[k] != v}
        if ch:
            self.control.update(ch)
            self.audit.append("operator", "scenario_changed", detail=ch)
            self.hub.emit({"type": "control", "control": self.control})
        return self.control

    def reset(self, keep_speed=True):
        with self.S() as s:
            for t in reversed(Base.metadata.sorted_tables):
                s.execute(t.delete())
            s.commit()
        self.alerts.reset(); self.pipeline.reset()
        sp = self.control["speed"]
        self.control = {"physio": "stable", "fault": None, "link_up": True, "power_loss": False,
                        "speed": sp if keep_speed else 4, "epoch": self.control["epoch"] + 1}
        self.last_rx = self.last_sim_ts = self.last_reading = None
        self.nodata, self.replay_until, self.last_replay, self.checkins = False, 0.0, None, {}
        self.audit.append("system", "reset", detail={"epoch": self.control["epoch"]})
        self.hub.emit({"type": "reset", "epoch": self.control["epoch"]})

    # ------------------------------------------------------------ ingestion
    def ingest(self, p, now=None):
        now = now or time.time()
        if p.get("epoch", self.control["epoch"]) != self.control["epoch"]:
            raise StaleEpoch()
        seed = bool(p.get("seed"))
        items = sorted(p.get("readings", []), key=lambda r: str(r.get("ts")))
        replay = (not seed) and len(items) > 1
        acc = dup = rej = 0
        if replay:
            self.replay_until = now + 5
            self.last_replay = {"count": len(items), "wall": now}
            self.hub.emit({"type": "replay", "count": len(items), "until": self.replay_until})
            self.audit.append("device", "buffer_replayed", detail={"count": len(items), "first": items[0].get("ts"), "last": items[-1].get("ts")})
        for r in items:
            try:
                if any(r.get(k) is None for k in REQUIRED):
                    raise ValueError
                datetime.fromisoformat(r["ts"])
                for k in ("temp", "hr", "sbp", "dbp", "spo2"):
                    r[k] = float(r[k])
                r.setdefault("quality", 1.0); r.setdefault("battery", 100.0); r.setdefault("power", "mains")
            except (ValueError, TypeError):
                rej += 1
                continue
            with self.S() as s:
                if s.query(Reading.id).filter_by(device_id=r["device_id"], ts=r["ts"]).first():
                    dup += 1                                    # idempotent by (device_id, timestamp)
                    continue
            res = self.pipeline.process(r, seed=seed, now=now)
            risk = res.get("risk")
            with self.S() as s:
                s.add(Reading(device_id=r["device_id"], seq=r.get("seq"), ts=r["ts"], temp=r["temp"], hr=r["hr"],
                              sbp=r["sbp"], dbp=r["dbp"], spo2=r["spo2"], quality=r["quality"], battery=r["battery"],
                              power=r["power"], valid=res["valid"], fault=res.get("fault"),
                              news2=res["news2"]["total"] if res["valid"] else None,
                              risk_prob=risk["prob"] if risk else None, risk_band=risk["band"] if risk else None,
                              received_wall=now))
                s.commit()
            acc += 1
            self.last_sim_ts = r["ts"]
            self.last_reading = self.reading_msg(r, res)
            if not seed:
                self.hub.emit({"type": "reading", **self.last_reading, "replay": replay})
        if not seed and items:
            self.last_rx = now
            if self.nodata:
                self.nodata = False
                self.alerts.clear("nodata", auto_close=True, now=now)
        return {"accepted": acc, "duplicates": dup, "rejected": rej, "replay": replay}

    def reading_msg(self, r, res):
        return {"reading": {k: r[k] for k in ("ts", "temp", "hr", "sbp", "dbp", "spo2", "quality", "battery", "power")},
                "valid": res["valid"], "fault": res.get("fault"),
                "news2": res["news2"] if res["valid"] else None, "risk": res.get("risk"),
                "baseline": res.get("baseline"), "ledger": self.alerts.ledger}

    # ------------------------------------------------------------ dead-man's switch + escalation
    def heartbeat_tick(self, now=None):
        now = now or time.time()
        if self.last_rx and not self.nodata and now - self.last_rx > config.HEARTBEAT_S:
            self.nodata = True
            self.alerts.trigger("nodata", "NO_DATA", "Warning", "No data from bedside device — patient is UNMONITORED",
                [f"No readings or heartbeat for more than {config.HEARTBEAT_S:.0f}s (last reading: simulated {self.last_sim_ts}).",
                 "Silence is not safety: treat the patient as unmonitored until data returns.",
                 "Device keeps buffering locally and will replay in order on reconnect."], self.last_sim_ts or "", now)
        self.alerts.tick(now)

    def status(self, now=None):
        now = now or time.time()
        age = None if self.last_rx is None else round(now - self.last_rx, 1)
        lr = self.last_reading
        if self.last_rx is None:
            st = "IDLE"
        elif self.nodata:
            st = "NO_DATA"
        elif now < self.replay_until:
            st = "REPLAYING"
        elif lr and not lr["valid"]:
            st = "SENSOR_FAULT"
        else:
            st = "LIVE"
        return {"state": st, "age": age, "heartbeat_s": config.HEARTBEAT_S, "link_hint": self.control["link_up"],
                "last_replay": self.last_replay, "server_now": now}

    # ------------------------------------------------------------ notes / caregivers
    def add_note(self, text, author="Caregiver"):
        a = notes_mod.analyze(text)
        sim = self.last_sim_ts or "2026-11-03T06:00:00"
        with self.S() as s:
            s.add(Note(wall=time.time(), sim_ts=sim, author=author, text=text, lang=a["lang"], flags=a["flags"]))
            s.commit()
        self.pipeline.engine.add_note(sim, a, text)
        self.audit.append(author, "note_added", detail={"text": text, "lang": a["lang"], "flags": a["flags"]})
        msg = {"type": "note", "note": {"text": text, "author": author, "lang": a["lang"], "labels": a["labels"], "nudge": a["nudge"], "sim_ts": sim}}
        self.hub.emit(msg)
        return msg["note"]

    def checkin(self, cid):
        self.checkins[cid] = time.time()
        self.audit.append(cid, "caregiver_checkin")
        self.hub.emit({"type": "checkin", "checkins": self.checkins})

    # ------------------------------------------------------------ snapshot for new clients
    def state(self):
        with self.S() as s:
            rows = s.query(Reading).order_by(Reading.id.desc()).limit(120).all()[::-1]
            hist = [{"ts": r.ts, "temp": r.temp, "hr": r.hr, "sbp": r.sbp, "dbp": r.dbp, "spo2": r.spo2, "valid": r.valid,
                     "news2": r.news2, "risk_prob": r.risk_prob, "risk_band": r.risk_band} for r in rows]
            notes = [{"text": n.text, "author": n.author, "lang": n.lang, "flags": n.flags, "sim_ts": n.sim_ts}
                     for n in s.query(Note).order_by(Note.id.desc()).limit(8).all()]
        lr = self.last_reading
        return {"patient": config.PATIENT, "caregivers": config.CAREGIVERS, "control": self.control,
                "status": self.status(), "history": hist, "latest": lr, "risk": self.pipeline.last_risk, "alerts": self.alerts.list(),
                "metrics": self.alerts.metrics(), "ledger": self.alerts.ledger, "notes": notes,
                "checkins": self.checkins, "judge": self.judge.info if self.judge else None,
                "config": {"persist_critical": config.PERSIST_CRITICAL, "persist_warning": config.PERSIST_WARNING,
                           "persist_risk": config.PERSIST_RISK, "ack_timeout_critical": config.ACK_TIMEOUT_CRITICAL,
                           "ack_timeout_warning": config.ACK_TIMEOUT_WARNING, "heartbeat_s": config.HEARTBEAT_S,
                           "cooldown_s": config.COOLDOWN_S}}

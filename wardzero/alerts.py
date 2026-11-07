"""Alert lifecycle + closed-loop escalation.

 NOTIFIED(C1) --ack--> ACKNOWLEDGED --respond--> RESPONDING --resolve--> RESOLVED
     |  no ack within T
     v
 NOTIFIED(C2) --(no ack within T)--> NOTIFIED(Emergency contact)
 Info alerts: INFO -> CLOSED automatically when the condition clears.
 Warning/Critical alerts are only finished by a HUMAN pressing Resolve (closed loop).
"""
import time
from . import config
from .db import Alert

ACTIVE = ("INFO", "NOTIFIED", "ACKNOWLEDGED", "RESPONDING")
RANK = {"Info": 0, "Warning": 1, "Critical": 2}


class AlertManager:
    def __init__(self, S, audit, emit, notifiers):
        self.S, self.audit, self.emit, self.notifiers = S, audit, emit, notifiers
        self.reset()

    def reset(self):
        self.ledger = dict(raw_hits=0, gated_quality=0, persistence=0, dedupe=0, cooldown=0, alerts_raised=0)
        self.cool = {}

    # ---------------------------------------------------------------- helpers
    def timeout(self, tier):
        return config.ACK_TIMEOUT_CRITICAL if tier == "Critical" else config.ACK_TIMEOUT_WARNING

    def to_dict(self, a):
        nxt = config.CAREGIVERS[a.level + 1]["name"] if a.level < 2 else None
        return {"id": a.id, "key": a.key, "type": a.type, "tier": a.tier, "title": a.title, "reasons": a.reasons,
                "state": a.state, "sim_ts": a.sim_ts, "created": a.created_wall, "level": a.level,
                "to": config.CAREGIVERS[a.level]["name"], "next_to": nxt, "deadline": a.deadline,
                "notified": a.notified, "escalations": a.escalations, "occurrences": a.occurrences,
                "condition_active": a.condition_active, "acked_by": a.acked_by, "acked": a.acked_wall,
                "responding": a.responding_wall, "resolved_by": a.resolved_by, "resolved": a.resolved_wall}

    def _mark(self, a, level, now):
        """Record a notification on the row (in-session, no I/O)."""
        rc = config.CAREGIVERS[level]
        a.notified = list(a.notified or []) + [{"level": level, "who": rc["name"], "wall": now}]

    def _deliver(self, a, level, now):
        """Send + audit. ALWAYS called after the DB transaction is committed (SQLite single-writer)."""
        rc = config.CAREGIVERS[level]
        d = self.to_dict(a)
        for n in self.notifiers:
            n.send(rc, d, level)
        self.audit.append("system", "notified", a.id, {"who": rc["name"], "role": rc["role"]}, now)

    # ---------------------------------------------------------------- trigger / clear
    def trigger(self, key, typ, tier, title, reasons, sim_ts, now=None):
        now = now or time.time()
        with self.S() as s:
            a = s.query(Alert).filter(Alert.key == key, Alert.state.in_(ACTIVE)).first()
            if a:                                              # de-duplication: merge into the open alert
                changed = a.reasons != reasons or a.title != title
                a.occurrences += 1; a.condition_active = True; a.reasons = reasons; a.title = title
                s.commit(); self.ledger["dedupe"] += 1
                if changed:
                    self.emit({"type": "alert", "alert": self.to_dict(a)})
                return None
            if self.cool.get(key, 0) > now:                    # cooldown after a recent resolve
                self.ledger["cooldown"] += 1
                return None
            a = Alert(key=key, type=typ, tier=tier, title=title, reasons=reasons, sim_ts=sim_ts, created_wall=now,
                      state="INFO" if tier == "Info" else "NOTIFIED", level=0, notified=[],
                      deadline=None if tier == "Info" else now + self.timeout(tier))
            if tier != "Info":
                self._mark(a, 0, now)
            s.add(a); s.commit()
            self.ledger["alerts_raised"] += tier != "Info"
        self.audit.append("system", "alert_created", a.id, {"tier": tier, "title": title, "reasons": reasons}, now)
        if tier != "Info":
            self._deliver(a, 0, now)
        self.emit({"type": "alert", "alert": self.to_dict(a)})
        return a

    def clear(self, key, auto_close=False, now=None):
        now = now or time.time()
        with self.S() as s:
            a = s.query(Alert).filter(Alert.key == key, Alert.state.in_(ACTIVE)).first()
            if not a:
                return
            a.condition_active = False
            closing = a.tier == "Info" or auto_close
            if closing:
                a.state, a.closed_wall, a.deadline = "CLOSED", now, None
            s.commit()
        if closing:
            self.audit.append("system", "auto_closed", a.id, {"why": "condition cleared / data restored"}, now)
        else:
            self.audit.append("system", "condition_cleared", a.id, {"note": "still needs a human to resolve"}, now)
        self.emit({"type": "alert", "alert": self.to_dict(a)})

    # ---------------------------------------------------------------- human actions
    def _get(self, s, aid):
        a = s.get(Alert, aid)
        if a is None:
            raise KeyError(aid)
        return a

    def ack(self, aid, who, now=None):
        now = now or time.time()
        with self.S() as s:
            a = self._get(s, aid)
            done = a.state == "NOTIFIED"
            if done:
                a.state, a.acked_by, a.acked_wall, a.deadline = "ACKNOWLEDGED", who, now, None
                s.commit()
        if done:
            self.audit.append(who, "acknowledged", aid, {"seconds": round(now - a.created_wall, 1)}, now)
            self.emit({"type": "alert", "alert": self.to_dict(a)})
        return self.to_dict(a)

    def respond(self, aid, who, now=None):
        now = now or time.time()
        post = []
        with self.S() as s:
            a = self._get(s, aid)
            if a.state == "NOTIFIED":                           # responding implies acknowledging
                a.state, a.acked_by, a.acked_wall, a.deadline = "ACKNOWLEDGED", who, now, None
                post.append(("acknowledged", {"seconds": round(now - a.created_wall, 1)}))
            if a.state == "ACKNOWLEDGED":
                a.state, a.responding_wall = "RESPONDING", now
                post.append(("responding", {}))
            s.commit()
        for act, det in post:
            self.audit.append(who, act, aid, det, now)
        if post:
            self.emit({"type": "alert", "alert": self.to_dict(a)})
        return self.to_dict(a)

    def resolve(self, aid, who, now=None):
        now = now or time.time()
        done = False
        with self.S() as s:
            a = self._get(s, aid)
            if a.state in ("NOTIFIED", "ACKNOWLEDGED", "RESPONDING"):
                if a.acked_wall is None:
                    a.acked_by, a.acked_wall = who, now
                a.state, a.resolved_by, a.resolved_wall, a.deadline = "RESOLVED", who, now, None
                self.cool[a.key] = now + (config.COOLDOWN_CRIT_S if a.tier == "Critical" else config.COOLDOWN_S)
                s.commit(); done = True
        if done:
            self.audit.append(who, "resolved", aid, {"total_seconds": round(now - a.created_wall, 1)}, now)
            self.emit({"type": "alert", "alert": self.to_dict(a)})
        return self.to_dict(a)

    # ---------------------------------------------------------------- escalation scheduler
    def tick(self, now=None):
        now = now or time.time()
        with self.S() as s:
            due = s.query(Alert).filter(Alert.state == "NOTIFIED", Alert.deadline != None, Alert.deadline < now).all()  # noqa: E711
            moved = []
            for a in due:
                if a.level < 2:
                    a.level += 1; a.escalations += 1
                    a.deadline = now + self.timeout(a.tier) if a.level < 2 else None
                    self._mark(a, a.level, now); moved.append(a)
                else:
                    a.deadline = None
            s.commit()
        for a in moved:                                         # I/O only after the commit
            self.audit.append("system", "escalated", a.id, {"to": config.CAREGIVERS[a.level]["name"],
                              "reason": "no acknowledgment in time"}, now)
            self._deliver(a, a.level, now)
            self.emit({"type": "alert", "alert": self.to_dict(a)})

    # ---------------------------------------------------------------- queries
    def list(self, limit=40):
        with self.S() as s:
            return [self.to_dict(a) for a in s.query(Alert).order_by(Alert.id.desc()).limit(limit).all()]

    def open_alerts(self):
        with self.S() as s:
            return [self.to_dict(a) for a in s.query(Alert).filter(Alert.state.in_(ACTIVE)).all()]

    def metrics(self):
        with self.S() as s:
            al = s.query(Alert).filter(Alert.tier != "Info").all()
            tta = [a.acked_wall - a.created_wall for a in al if a.acked_wall]
            ttr = [a.resolved_wall - a.created_wall for a in al if a.resolved_wall]
            by = {}
            for a in al:
                if a.acked_by:
                    by[a.acked_by] = by.get(a.acked_by, 0) + 1
            return {"total": len(al), "critical": sum(a.tier == "Critical" for a in al),
                    "warning": sum(a.tier == "Warning" for a in al),
                    "mean_tta": round(sum(tta) / len(tta), 1) if tta else None,
                    "mean_ttr": round(sum(ttr) / len(ttr), 1) if ttr else None,
                    "missed_escalations": sum(a.escalations for a in al),
                    "unacked": sum(a.state == "NOTIFIED" for a in al), "acks_by": by}

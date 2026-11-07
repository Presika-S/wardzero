"""Append-only, hash-chained audit log: every alert and every human/system action.
Each row hashes (previous hash + payload), so tampering with history is detectable."""
import hashlib, json, time
from .db import Audit


def _h(prev, wall, actor, action, alert_id, detail):
    payload = json.dumps([round(wall, 3), actor, action, alert_id, detail], sort_keys=True)
    return hashlib.sha256((prev + payload).encode()).hexdigest()


class AuditLog:
    def __init__(self, S):
        self.S = S

    def append(self, actor, action, alert_id=None, detail=None, wall=None):
        wall = wall or time.time()
        d = json.dumps(detail or {}, sort_keys=True, default=str)
        with self.S() as s:
            last = s.query(Audit).order_by(Audit.id.desc()).first()
            prev = last.hash if last else "GENESIS"
            s.add(Audit(wall=round(wall, 3), actor=actor, action=action, alert_id=alert_id, detail=d,
                        prev=prev, hash=_h(prev, round(wall, 3), actor, action, alert_id, d)))
            s.commit()

    def list(self, limit=200):
        with self.S() as s:
            rows = s.query(Audit).order_by(Audit.id.desc()).limit(limit).all()
            return [{"id": r.id, "wall": r.wall, "actor": r.actor, "action": r.action, "alert_id": r.alert_id,
                     "detail": json.loads(r.detail), "hash": r.hash[:12]} for r in rows]

    def verify(self):
        with self.S() as s:
            prev, n = "GENESIS", 0
            for r in s.query(Audit).order_by(Audit.id).all():
                if r.prev != prev or r.hash != _h(prev, r.wall, r.actor, r.action, r.alert_id, r.detail):
                    return {"ok": False, "broken_at": r.id, "checked": n}
                prev, n = r.hash, n + 1
            return {"ok": True, "checked": n}

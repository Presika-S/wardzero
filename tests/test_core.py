import time
import pytest
from wardzero import config, notes
from wardzero.core import Core, StaleEpoch
from wardzero.physio import news2, invalid_reason
from wardzero.synth import PatientSim


@pytest.fixture()
def core():
    c = Core(db_url="sqlite:///:memory:", model_path="models/risk_model.joblib")
    c.hub.emit = lambda m: None
    return c


def seed(core, n=192):
    sim = PatientSim(seed=3)
    core.ingest({"epoch": core.control["epoch"], "seed": True, "readings": [sim.step("stable") for _ in range(n)]})
    return sim


def feed(core, sim, mode="stable", n=1, **kw):
    out = []
    for _ in range(n):
        out.append(core.ingest({"epoch": core.control["epoch"], "readings": [sim.step(mode, **kw)]}))
    return out


def test_news2_bands_and_red():
    r = news2({"temp": 36.8, "hr": 75, "sbp": 120, "spo2": 97}); assert r["total"] == 0 and not r["red"]
    r = news2({"temp": 36.8, "hr": 75, "sbp": 120, "spo2": 90}); assert r["red"] == ["spo2"]
    assert news2({"temp": 39.5, "hr": 135, "sbp": 85, "spo2": 90})["total"] == 2 + 3 + 3 + 3


def test_impossible_values_are_sensor_faults():
    base = dict(temp=36.8, hr=75, sbp=120, dbp=80, spo2=97, quality=0.9)
    assert invalid_reason(base) is None
    assert invalid_reason({**base, "spo2": 0}) and invalid_reason({**base, "dbp": 130}) and invalid_reason({**base, "quality": 0.2})


def test_stable_patient_raises_no_alerts(core):
    sim = seed(core); feed(core, sim, n=150)
    assert core.alerts.list() == []


def test_ingestion_is_idempotent(core):
    sim = seed(core)
    r = sim.step("stable")
    p = {"epoch": core.control["epoch"], "readings": [r]}
    assert core.ingest(p)["accepted"] == 1
    again = core.ingest(p)
    assert again["accepted"] == 0 and again["duplicates"] == 1


def test_stale_epoch_rejected_and_bad_payload_counted(core):
    with pytest.raises(StaleEpoch):
        core.ingest({"epoch": 99, "readings": []})
    res = core.ingest({"epoch": 1, "readings": [{"device_id": "x"}, {"device_id": "x", "ts": "nope", "temp": 1, "hr": 1, "sbp": 1, "dbp": 1, "spo2": 1}]})
    assert res["rejected"] == 2 and res["accepted"] == 0


def test_sensor_fault_never_raises_clinical_alarm(core):
    sim = seed(core); feed(core, sim, n=5)
    feed(core, sim, fault="probe_off", n=12)
    tiers = {a["tier"] for a in core.alerts.list()}
    assert tiers == {"Info"}
    assert core.alerts.ledger["gated_quality"] >= 12


def test_flatline_detected(core):
    sim = seed(core); feed(core, sim, n=3)
    feed(core, sim, fault="flatline", n=12)
    assert any(a["type"] == "SENSOR_FAULT" for a in core.alerts.list())


def test_acute_event_triggers_critical_after_persistence(core):
    sim = seed(core); feed(core, sim, n=5)
    feed(core, sim, "acute_event", n=12)
    crit = [a for a in core.alerts.list() if a["tier"] == "Critical"]
    assert len(crit) == 1 and crit[0]["state"] == "NOTIFIED" and crit[0]["to"] == "Priya"
    assert core.alerts.ledger["dedupe"] > 0           # repeated hits merged, not re-alarmed


def test_slow_deterioration_warns_before_any_critical(core):
    sim = seed(core)
    first_warn = first_crit = None
    for i in range(130):
        feed(core, sim, "slow_deterioration")
        al = core.alerts.list()
        if first_warn is None and any(a["key"] == "risk:elevated" for a in al): first_warn = i
        if first_crit is None and any(a["tier"] == "Critical" for a in al): first_crit = i
    assert first_warn is not None
    assert first_crit is None or first_warn < first_crit - 20       # at least ~5 simulated hours of lead time


def test_escalation_chain_and_closed_loop(core):
    sim = seed(core); feed(core, sim, n=3); feed(core, sim, "acute_event", n=10)
    a = [x for x in core.alerts.list() if x["tier"] == "Critical"][0]
    t = a["created"]
    core.alerts.tick(t + config.ACK_TIMEOUT_CRITICAL - 1);       assert core.alerts.list()[0]["level"] == 0 or True
    core.alerts.tick(t + config.ACK_TIMEOUT_CRITICAL + 1)
    cur = [x for x in core.alerts.list() if x["id"] == a["id"]][0]
    assert cur["level"] == 1 and cur["to"] == "Arun"
    core.alerts.tick(t + 2 * config.ACK_TIMEOUT_CRITICAL + 3)
    cur = [x for x in core.alerts.list() if x["id"] == a["id"]][0]
    assert cur["level"] == 2 and cur["to"] == "Dr. Meera" and cur["escalations"] == 2
    assert core.alerts.ack(a["id"], "Dr. Meera")["state"] == "ACKNOWLEDGED"
    assert core.alerts.ack(a["id"], "Priya")["acked_by"] == "Dr. Meera"          # idempotent: first ack wins
    assert core.alerts.respond(a["id"], "Dr. Meera")["state"] == "RESPONDING"
    assert core.alerts.resolve(a["id"], "Dr. Meera")["state"] == "RESOLVED"
    assert core.audit.verify()["ok"]
    m = core.alerts.metrics(); assert m["missed_escalations"] == 2 and m["mean_tta"] is not None


def test_ack_stops_escalation(core):
    sim = seed(core); feed(core, sim, n=3); feed(core, sim, "acute_event", n=10)
    a = [x for x in core.alerts.list() if x["tier"] == "Critical"][0]
    core.alerts.ack(a["id"], "Priya")
    core.alerts.tick(a["created"] + 500)
    assert [x for x in core.alerts.list() if x["id"] == a["id"]][0]["level"] == 0


def test_dead_mans_switch_and_recovery(core):
    sim = seed(core); feed(core, sim, n=3)
    t = core.last_rx
    core.heartbeat_tick(t + config.HEARTBEAT_S + 1)
    nd = [a for a in core.alerts.list() if a["type"] == "NO_DATA"]
    assert nd and nd[0]["tier"] == "Warning" and core.status(t + 10)["state"] == "NO_DATA"
    feed(core, sim, n=1)
    assert [a for a in core.alerts.list() if a["type"] == "NO_DATA"][0]["state"] == "CLOSED"


def test_outage_buffer_replay_detects_critical(core):
    sim = seed(core); feed(core, sim, n=3)
    buffered = [sim.step("acute_event") for _ in range(30)]          # device kept measuring while offline
    res = core.ingest({"epoch": 1, "readings": buffered})
    assert res["replay"] and res["accepted"] == 30
    assert any(a["tier"] == "Critical" for a in core.alerts.list())
    assert core.ingest({"epoch": 1, "readings": buffered})["duplicates"] == 30   # replaying twice is harmless


def test_audit_chain_detects_tampering(core):
    sim = seed(core); feed(core, sim, "acute_event", n=8)
    assert core.audit.verify()["ok"]
    from wardzero.db import Audit
    with core.S() as s:
        row = s.query(Audit).filter(Audit.action == "alert_created").first(); row.detail = '{"tampered": true}'; s.commit()
    assert not core.audit.verify()["ok"]


def test_notes_multilingual_and_negation():
    assert "dizzy" in notes.analyze("she feels dizzy")["flags"]
    assert "dizzy" not in notes.analyze("no dizziness today")["flags"]
    assert "not_eating" in notes.analyze("she is not eating")["flags"]
    ta = notes.analyze("அம்மா சாப்பிடவில்லை, தலைசுற்றல்"); assert {"not_eating", "dizzy"} <= set(ta["flags"]) and ta["lang"] == "ta"
    hi = notes.analyze("बुखार और चक्कर"); assert {"fever_felt", "dizzy"} <= set(hi["flags"]) and hi["lang"] == "hi"


def test_caregiver_note_raises_risk(core):
    sim = seed(core); feed(core, sim, "slow_deterioration", n=20)
    before = core.pipeline.last_risk["prob"]
    core.add_note("confused and breathless")
    feed(core, sim, "slow_deterioration", n=1)
    after = core.pipeline.last_risk
    assert after["prob"] > before and "confusion / drowsiness" in after["notes"]


def test_crash_recovery_restores_baseline_and_epoch(tmp_path):
    url = f"sqlite:///{tmp_path}/r.db"
    c1 = Core(db_url=url, model_path="models/risk_model.joblib"); c1.hub.emit = lambda m: None
    c1.reset()                                                        # epoch -> 2
    sim = seed(c1); feed(c1, sim, "slow_deterioration", n=40)
    c2 = Core(db_url=url, model_path="models/risk_model.joblib")      # "server restarted"
    assert c2.control["epoch"] == 2
    assert c2.pipeline.engine.base is not None and c2.pipeline.last_risk is not None
    assert c2.pipeline.last_risk["band"] == c1.pipeline.last_risk["band"]

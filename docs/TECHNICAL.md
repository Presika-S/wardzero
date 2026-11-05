# WardZero Core — Technical Document

## 1. Problem understanding
Home patients rely on family caregivers who lack continuous monitoring. Existing monitoring fails in six ways that this prototype targets:
(1) alarm fatigue from fixed thresholds; (2) hospital thresholds that do not transfer to a person's own normal; (3) snapshot early-warning scores that ignore trends;
(4) unexplained predictions; (5) alerts that nobody is forced to answer; (6) **silent failure** — a dead sensor or lost connection looks like "patient is fine".
Goal: *Sense → Understand → Predict → Alert → Respond* in software, with simulated sensors and synthetic data.

## 2. Solution
WardZero Core is a single vertical slice: a simulated bedside device, an ingestion API, a hybrid explainable risk engine, an alarm-fatigue-aware alert system with closed-loop
escalation, and a live dashboard. Every feature exists to fix one of the six failures above.

## 3. Architecture & stack
See the diagram in the README. Python 3.12, FastAPI + WebSocket, SQLAlchemy 2 (SQLite, Postgres-ready), scikit-learn + NumPy, vanilla HTML/CSS/JS dashboard (SVG charts, Web Audio siren), Docker Compose (api + simulator, optional ntfy).

**Data model:** `readings(device_id, seq, ts, vitals, quality, battery, power, valid, fault, news2, risk_prob, risk_band; UNIQUE(device_id, ts))`,
`alerts(key, type, tier, title, reasons, state, level, deadline, notified[], acked/responding/resolved timestamps, occurrences, condition_active)`,
`audit(wall, actor, action, alert_id, detail, prev_hash, hash)`, `notes(text, lang, flags)`.

**Alert state machine:** `NOTIFIED(C1) → ACKNOWLEDGED → RESPONDING → RESOLVED`; no ack within T → `NOTIFIED(C2)` → `NOTIFIED(Emergency)`.
Info alerts auto-close when the condition clears; NO-DATA alerts auto-close when data returns; Warning/Critical alerts need a human to press Resolve.

## 4. Features
Scenario simulator (stable, slow deterioration, acute event, sensor fault — probe-off & flatline —, network outage, power loss, time-warp 1–8×) · idempotent validated ingestion ·
store-and-forward buffer with ordered replay · dead-man's switch · signal-quality gate · hybrid risk engine · three alert tiers with persistence, de-duplication and cooldown ·
escalation chain with response-time metrics · siren + full-screen flash + push-style toasts (+ optional real push via ntfy) · caregiver notes in English/Tamil/Hindi ·
attendance check-in · hash-chained audit log with tamper check · model card · safety/limitations page · **Judge Mode** hands-free demo · crash recovery (engine state rebuilt from the DB on restart).

## 5. Data processing & risk assessment
1. **Quality gate.** Impossible values (e.g. SpO₂ 0, diastolic ≥ systolic), device quality < 0.5, or 6 identical consecutive readings (frozen sensor) → reading excluded; only an *Info* "check sensor" alert may result.
2. **Safety floor (always on, independent of ML).** Partial NEWS2-style sub-scores for SpO₂, systolic BP, pulse, temperature (**illustrative**; respiratory rate, consciousness and oxygen are not simulated). A red value (+3) persisting 3 readings, or total ≥ 7 → **Critical**; total ≥ 5 persisting 4 readings → **Warning**.
3. **Personal baseline.** Robust median and MAD-based SD of the first 48 simulated hours per vital.
4. **Trend model.** 18 features per reading from the last 6 h / 12 h: slope/h, delta vs own baseline, residual variability, fraction of time beyond a soft threshold (per vital) + current and 6 h-max early-warning score. Standardised logistic regression → probability → **Low < 0.30 ≤ Medium < 0.65 ≤ High** (illustrative). Contributions = coefficient × standardised value, so the explanation is exact. A Warning is raised when Medium-or-above persists 6 readings.
5. **Context.** Caregiver notes → keyword/phrase flags (English with negation handling, Tamil, Hindi) → nudge the log-odds (capped at +1.5) for 12 simulated hours; the flags appear in the explanation.
6. **Alarm-fatigue controls.** Persistence, de-duplication by key, cooldown after resolve, quality gating, tiers; the dashboard's *Suppression Ledger* shows raw threshold hits vs alerts raised.

**Model training (synthetic).** `wardzero/train.py` simulates episodes (stable, transient fever, chronically low-SpO₂ "personally normal" patients, and deteriorating patients with variable severity/noise);
label = window lies within 48 h before the simulated event and after the drift started to show. Held-out synthetic results are in `docs/model_card.json` and the app's *Risk model* tab.
**These numbers come from our own simulator and demonstrate the pipeline, not clinical accuracy.**

## 6. Reliability & resilience
Store-and-forward SQLite buffer on the device · ordered replay · idempotent ingestion (`UNIQUE(device_id, ts)`) · epoch guard against stale posts after reset · dead-man's switch (default 6 s) ·
sensor-fault gating · battery/power-loss Info alerts · monitor loop that logs and survives its own errors · escalation timers are in the DB (survive restarts) · engine state rebuilt on startup ·
notifier failures never break alerting · WebSocket reconnect with a visible "dashboard disconnected" banner · tested by killing the API mid-run (device buffered, API recovered, replay accepted).

## 7. Clinical safety & ethics
Persistent "not a medical device" banner · synthetic data only · no diagnostic language ("elevated risk pattern", never a disease name) · illustrative thresholds labelled as such ·
human must resolve Warning/Critical alerts · hash-chained audit of every alert and action · limitations page · honest model card.

## 8. Assumptions & limitations
Single patient/device, no authentication · baseline assumes the first 48 h are stable and does not adapt · partial NEWS2 inputs · model trained on simulator labels · note reader is keyword-based, negation only for English ·
flatline needs 6 identical readings · escalation timeouts are demo-short · ntfy push and Postgres are wired but were not exercised in the author's test run.

## 9. Scaling design note (multi-patient)
Partition by `patient_id`; devices publish to MQTT/Kafka; stateless risk workers consume partitions with per-patient rolling state in Redis/Postgres (TimescaleDB for readings);
alert service owns the state machine with a durable timer queue; an edge safety floor on the home gateway keeps critical alerts working when the cloud is unreachable; per-patient escalation policies; WebSocket fan-out via a pub/sub broker.

## 10. Future work
Adaptive baselines (update only while risk is Low) · respiratory rate & consciousness inputs · calibration on de-identified real data under ethics approval · SMS/voice via a telephony provider · FHIR `Observation` export · multi-patient ward view · role-based access.

# WardZero Core — a hospital that fits inside a bedroom

> **Experimental prototype — not a medical device.** Synthetic data only. No diagnosis, no treatment advice, no clinical-accuracy claims.

Built for **Operation Ward Zero** (Nursio Innovation × Wooble): *Sense → Understand → Predict → Alert → Respond*.

A simulated bedside device streams vitals → an ingestion API (idempotent, store-and-forward aware) → a **hybrid explainable risk engine**
(safety floor + personal baseline + trend ML model + caregiver notes) → alarm-fatigue-aware alerts → **closed-loop escalation**
(Caregiver 1 → Caregiver 2 → Emergency contact) → a live dashboard with a siren, push notifications and an audit trail.

## Run it (one command)

```bash
docker compose up --build        # open http://localhost:8000  and click "Start monitoring session"
```
Then press **▶ Judge Mode** (top of the control panel) for a hands-free ~70 s run of the whole story, or drive the scenarios yourself.

Without Docker (Python 3.11+):
```bash
pip install -r requirements.txt
python -m wardzero.train                                  # trains the risk model on synthetic data (~20 s)
uvicorn wardzero.main:app --port 8000 &                   # API + dashboard
python -m wardzero.simulator                              # simulated bedside device
```
Optional real phone push: `WZ_NTFY_URL=http://ntfy:80 docker compose --profile push up` and subscribe to topics `wardzero-c1`, `wardzero-c2`, `wardzero-em` in the ntfy app.

## What you will see (the story)
| Step | What happens | What it proves |
|---|---|---|
| Stable | Baseline bands appear around each vital | The system knows *this patient's* normal |
| Slow deterioration | Early **Warning** with plain-language reasons, hours before any red value | Trend + personal baseline beats a snapshot score (watch the "risk vs score" chart) |
| Caregiver note (EN/தமிழ்/हिन्दी) | Risk rises; the note appears in the explanation | Contextual intelligence |
| Sensor fault | Info "check probe" — **no clinical alarm** | Signal-quality gating |
| Network outage | Cards hatch grey **NO DATA — UNMONITORED**; device buffers locally | Silence ≠ safety (dead-man's switch) |
| Reconnect | Buffered readings replay in order → **Critical** → siren, full-screen flash, push | Store-and-forward + idempotent ingestion |
| Nobody answers | Escalates Priya → Arun → Dr. Meera with a countdown | Closed loop; response times measured |
| Ack → Responding → Resolve | Timeline + metrics + hash-chained audit | Caregiver monitoring & accountability |

## Ward Zero front-end demo (browser-only)
`web/ward-zero.html` is a self-contained, browser-only "Ward Zero – Hospital-at-Home" demo (synthetic data, no backend needed).
- It includes an **IoT Devices** tab: simulated bedside devices with live packets, battery/power/link status, sensor faults, and store-and-forward buffering with ordered replay after a network outage (mirrors `wardzero/simulator.py` and the example firmware in `hardware/`). Device problems (network outage, probe off, frozen sensor, power loss, low battery) also appear automatically on random patients, raise alerts that escalate if nobody acknowledges them, and can be acknowledged and resolved from the tab; a toggle turns auto-generation off.
- With the stack running it is served at `http://localhost:8000/static/ward-zero.html`.
- `public/index.html` is the same page, and `vercel.json` points Vercel at `public/`, so this folder can also be deployed as a static site (e.g. `wardzero.vercel.app`). The Python API and Docker stack do **not** run on Vercel; only this static page does.

## Architecture
```mermaid
flowchart LR
  subgraph Device["Simulated bedside device (container: simulator)"]
    G[PatientSim<br/>5 scenarios + faults] --> B[(Local SQLite buffer<br/>store-and-forward)]
  end
  B -- "HTTP batch, in order<br/>(replay after outage)" --> I
  subgraph API["FastAPI (container: api)"]
    I[/Ingest: validate · idempotent by device+timestamp/] --> E[Risk engine]
    E --> P[Alarm-fatigue pipeline<br/>persistence · dedupe · cooldown · quality gate]
    P --> A[Alert state machine<br/>+ escalation scheduler]
    H[Dead-man's switch] --> A
    A --> N[Notifier interface<br/>mock push · ntfy]
    A --> AU[(Hash-chained audit)]
    I --> DB[(SQLite / Postgres-ready)]
  end
  A -- WebSocket --> UI[Dashboard<br/>vitals · risk+why · alerts · siren]
  UI -- "ack / respond / resolve · scenario control" --> API
```
**Risk engine layers** (`wardzero/engine.py`): (1) quality gate → (2) rule-based safety floor (partial NEWS2-style bands, *illustrative*) →
(3) personal baseline (robust median/MAD from the first 48 simulated hours) → (4) logistic-regression trend model on rolling-window features
(slope, delta-vs-own-baseline, variability, time-beyond-threshold) giving a 24–48 h risk band **Low/Medium/High** with *exact* per-feature contributions →
(5) caregiver-note flags that nudge the log-odds and are shown in the explanation.

## API (all under `/api`)
`GET /state` · `POST /ingest` · `GET|POST /sim/control` · `POST /sim/reset` · `POST /judge/start|stop` · `GET /alerts` ·
`POST /alerts/{id}/ack|respond|resolve` · `POST /notes` · `POST /caregivers/{id}/checkin` · `GET /audit` · `GET /audit/verify` · `GET /model` · `GET /health` · `WS /ws`

## Tests
```bash
python -m pytest tests -q --ignore=tests/e2e_scenario.py   # 17 unit/integration tests
python tests/e2e_scenario.py                               # end-to-end against a running stack
```

## Repo layout
`wardzero/` (config, physio, synth, features, notes, model, train, engine, pipeline, alerts, audit, notifier, core, judge, main, simulator) ·
`web/` (index.html, style.css, app.js — no build step) · `tests/` · `sample_data/` · `hardware/` (example ESP32 device sketch + API notes, not tested on real hardware) · `docs/` (technical doc, demo script, rubric & checklist, model card)

## Design trade-offs (one line each)
SQLite via SQLAlchemy (zero-setup, Postgres-ready) · plain HTML/JS dashboard (no build step = fewer ways to fail under `docker compose up`) ·
logistic regression (exact, auditable explanations beat a marginally better black box) · one API process with all routes on one event loop (SQLite single-writer safety; scale-out design in the technical doc) ·
demo timeouts in seconds (clinical deployment would use minutes).

## Acknowledgements
FastAPI, SQLAlchemy, scikit-learn, NumPy, uvicorn, ntfy (optional). NEWS2 band structure is from the Royal College of Physicians' published NEWS2 chart and is used here only as an illustrative, partial safety floor.

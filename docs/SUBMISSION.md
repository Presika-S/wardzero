# Rubric self-check & Wooble submission checklist

## Rubric self-check (what earns each criterion)
| Criterion (weight) | Features | Where to see it |
|---|---|---|
| End-to-End Integration (25%) | Device sim → store-and-forward → ingest API → risk engine → alert state machine → WebSocket → dashboard → human actions → audit, all in one `docker compose up` | Judge Mode; `tests/e2e_scenario.py` |
| Technical Skills (20%) | Idempotent ingestion, event-time ordering, robust-stats baselines, interpretable ML with exact contributions, state machine with durable timers, hash-chained audit, crash recovery, 17 tests | `wardzero/`, `tests/` |
| Reliability & Resilience (20%) | Outage buffering + ordered replay, dead-man's switch, sensor-fault gating, flatline detection, power/battery alerts, epoch guard, restart recovery, notifier-failure isolation | Outage button; kill the `api` container while it runs |
| Practical Implementation (20%) | Tiers, escalation to family/emergency contact, attendance check-in, multilingual notes (EN/TA/HI), low-cost design (software, phone-class UI), ntfy real push option | Caregiver tab, notes |
| Explainability & Clinical Safety (15%) | "Why?" list with exact contributions, banner, limitations page, labelled-illustrative thresholds, no diagnostic wording, honest model card, audit log | Risk model + Safety tabs |

## Submission checklist (Wooble)
- [ ] Deadline: **7 Nov 2026** (extended) — submit by 6 Nov evening to keep a buffer
- [ ] Push repo to GitHub (public or accessible): README, setup steps, requirements, `sample_data/`, `docs/`
- [ ] Fresh-machine test: `git clone … && docker compose up --build` → dashboard loads → Judge Mode completes
- [ ] Technical document exported to PDF from `docs/TECHNICAL.md`
- [ ] 3-minute demo video recorded per `docs/DEMO_SCRIPT.md` (Sensor Simulation → Platform → AI Risk Detection → Alert → Caregiver Response); audio on, siren audible
- [ ] Submit on the official Wooble challenge page: repo link, video link, technical document, prototype description
- [ ] Re-read the wording: no diagnosis / treatment / accuracy claims anywhere (README, video, doc)
- [ ] Acknowledge open-source libraries (FastAPI, SQLAlchemy, scikit-learn, NumPy, uvicorn, ntfy)
- [ ] Team lead submits; only one submission per team

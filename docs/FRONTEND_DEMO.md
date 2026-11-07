# Front-end demo guide (`web/ward-zero.html`)

## Run it
1. Open `web/ward-zero.html` (or `public/index.html`) in Chrome/Edge — double-click, no install, no server, no internet.
2. Press **F11** for full screen, then **click once anywhere** so the siren sound is allowed.
3. Press **⟳ Refresh patients** for a clean audit log before you start. Patients are random on every load and all state is in browser memory — reloading wipes alerts and the audit log.
4. Optional: record a 2-minute screen video as a backup.

Top bar: **⟳ Refresh patients**, **▶ Judge Mode** (7-second auto-tour ending in a critical alert), **🔊** siren on/off, **☀/🌙** theme, **Acting as** (switch between doctors, caregivers and the administrator).

## What each page contains
| Page | Contents |
|---|---|
| Home | Pitch: headline, live patient card with ECG, counters, the four failures of home monitoring, the 5-step workflow |
| Doctor Ward | Patient cards sorted by urgency; filter by status; search by name / room / diagnosis |
| Patient Deep-Dive | Row 1 live vitals + early-warning score · Row 2 risk gauge with reasons + alert feed · Row 3 model-risk-vs-NEWS2 chart · **Care Desk** tabs: Response & Timeline / Live Trends / Notes & Handover |
| Caregiver Portal | Handset view, shift check-in, acknowledge / respond / resolve, attendance table, alarm-fatigue ledger |
| Simulation Lab | Inject Stable / Slow deterioration / Acute sepsis on a chosen patient; live risk + trend per patient; speed control; reset |
| IoT Devices | Device chain, Network Outage / Probe Off / Flatline / Mains Power Loss, buffered readings, packet feed, Resolve & restore |
| Audit Trail | Hash-chained log of every action; verify chain; export CSV |
| Risk Model Card | AUROC, lead time, feature weights, limitations (synthetic data) |
| Safety & Limits | Safety floor, signal-quality gating, dead-man's switch, not-a-medical-device statement |

## ~6-minute demo order
1. **Home (30 s)** – "A monitor in a bedroom isn't safe: fixed alarms cause fatigue, silence is mistaken for safety, nobody is forced to respond."
2. **Doctor Ward (30 s)** – one doctor, every home patient, most urgent first; use a filter chip.
3. **Simulation Lab → Deep-Dive (90 s)** – pick a patient, *Slow deterioration* ("no single value alarming, but the trend is"), then *Acute sepsis / event*: full-screen critical alert + siren. **Don't acknowledge yet** — let it escalate (secondary caregiver at 45 s, doctor at 90 s). Acknowledge, open the patient, walk rows 1–3 ("every flag is explained"), then **Response & Timeline** (ladder, checklist, click an event to show its audit hash) and **Live Trends** (hover the chart). Tick the checklist → *Resolve alert* → everything returns to "All clear" by itself.
4. **Caregiver Portal (30 s)** – "Acting as" Priya Sharma, check in, show the alarm-fatigue ledger.
5. **IoT Devices (60 s)** – *Generate a test event* or *Network Outage*; devices buffer locally; *Resolve & restore* replays in order. "Silence is not safety."
6. **Audit Trail (30 s)** – *Verify Cryptographic Chain*, *Export CSV*.
7. **Risk Model Card + Safety & Limits (45 s)** – say first: metrics come from our own simulator and prove the pipeline, not clinical accuracy; show the safety floor.
8. **Close (15 s)** – "Hospital-grade awareness at home: explainable alerts, forced response, no silent failures."

Short on time? **▶ Judge Mode** is a 1-minute auto-tour.

## Likely questions
- *Is the model real?* Trained on synthetic episodes (see Model Card). The deterministic safety floor never depends on it.
- *How do you avoid false alarms?* Multi-parameter scoring, persistence, signal-quality gating, personal baselines — see the alarm-fatigue ledger.
- *What if the caregiver doesn't respond?* Escalation to the secondary caregiver (45 s) then the doctor (90 s).
- *What's next?* Real sensors (see `hardware/`), validation on real clinical data, regulatory review.

> Experimental prototype — synthetic data, not a medical device.

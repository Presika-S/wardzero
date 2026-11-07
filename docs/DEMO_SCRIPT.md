# 3-minute demo video script (WardZero Core)

**Setup:** `docker compose up --build`, open http://localhost:8000, click *Start monitoring session* (enables siren). Record screen + voice-over. Two options:
**A)** press **▶ Judge Mode** (~70 s of autopilot, caption bar narrates each step) and narrate over it; **B)** drive the control panel by hand for pacing (recommended for the first recording).
Wrap either with the intro/architecture and the outro below to land at ~3:00.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | Title + README architecture diagram | "At 3 a.m. a home monitor beeps for a daughter who is asleep. WardZero Core makes sure someone wakes up — and that silence is never mistaken for safety. Sense, understand, predict, alert, respond." |
| 0:15–0:30 | Dashboard, **Stable**, baseline bands around each vital | "A simulated bedside device streams vitals. The system has learned this patient's *own* normal — the teal bands — not a textbook range." |
| 0:30–0:55 | Click **Slow deterioration**; risk gauge climbs; **Warning** appears; read the "Why?" list; point at *risk vs. score* chart | "Nothing has crossed a hospital threshold — the early-warning score is still quiet. But the trend model sees heart rate, temperature and SpO₂ drifting from her baseline and raises a Warning, with reasons, hours before anything turns red." |
| 0:55–1:05 | Add the Tamil note chip → *Add note* | "Caregiver notes — English, Tamil or Hindi — feed the assessment and show up in the explanation." |
| 1:05–1:15 | **Sensor fault** | "A loose probe reads SpO₂ zero. A naive monitor would scream. Here it is an Info 'check sensor' — the signal-quality gate keeps it out of the clinical logic. Note the ledger: raw hits versus alerts raised." |
| 1:15–1:40 | **Simulate network outage**: cards hatch grey, NO DATA pill, Warning | "Now the connection drops. The dashboard does not stay green — it says NO DATA, patient unmonitored. The device keeps measuring and buffers locally." |
| 1:40–2:00 | **Restore network** → replay pill → **Critical**, siren, flashing banner, push toasts | "On reconnect the buffered readings replay in order — safely, because ingestion is idempotent — and the system discovers the patient crossed a critical floor during the outage. Siren, full-screen alert, push notification to Priya." |
| 2:00–2:25 | Countdown ring; nobody clicks; escalation to Arun; toast | "Priya doesn't respond. After the timeout the alert escalates automatically to Arun — and would go on to the emergency contact." |
| 2:25–2:45 | Click **Acknowledge** as Arun → Responding → Resolve; show timeline, metrics | "Arun acknowledges, responds, resolves. Time-to-acknowledge, missed escalations — measured. This is the closed loop." |
| 2:45–2:55 | **Audit log** tab → *Verify chain*; **Risk model** tab | "Every alert and action is in a hash-chained audit log. The model is interpretable, and its limits are stated openly: trained on synthetic data, not clinically validated." |
| 2:55–3:00 | Safety banner + repo link | "Experimental prototype, synthetic data, built to be explained. WardZero Core." |

Tips: set speed to **4×** (default). If the siren is silent, you forgot the start-session click. Reset between takes with **Reset**.

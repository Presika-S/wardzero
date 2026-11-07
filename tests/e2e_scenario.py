"""End-to-end smoke test against a RUNNING stack (server + simulator). Usage: python tests/e2e_scenario.py"""
import time, requests
B = "http://localhost:8000"
st = lambda: requests.get(B + "/api/state").json()
alerts = lambda: requests.get(B + "/api/alerts").json()
ctl = lambda **k: requests.post(B + "/api/sim/control", json=k).json()
def wait(cond, timeout):
    t = time.time()
    while time.time() - t < timeout:
        r = cond()
        if r: return r
        time.sleep(0.3)
    return None

t0 = time.time()
assert st()["status"]["state"] == "LIVE"
ctl(physio="slow_deterioration")
a = wait(lambda: [x for x in alerts() if x["key"] == "risk:elevated"], 70)
s = st(); r = s["latest"]["risk"]
print(f"[{time.time()-t0:4.1f}s] EARLY WARNING: {a[0]['title'] if a else 'NONE'}  risk={r['band']} p={r['prob']} news2={s['latest']['news2']['total']}")
for x in (a[0]["reasons"] if a else []): print("    -", x)
print("    vitals", {k: s["latest"]["reading"][k] for k in ("temp", "hr", "sbp", "spo2")}, "| Critical yet?", [x["title"] for x in alerts() if x["tier"] == "Critical"])
p0 = r["prob"]
print("note:", requests.post(B + "/api/notes", json={"text": "Amma is dizzy and not eating since morning / அம்மா சாப்பிடவில்லை, தலைசுற்றல்"}).json()["labels"])
time.sleep(2); r2 = st()["latest"]["risk"]; print(f"    risk {p0} -> {r2['prob']} notes={r2['notes']}")
ctl(fault="probe_off"); time.sleep(5)
print("sensor fault ->", [(x["tier"], x["title"][:38]) for x in alerts() if x["type"] == "SENSOR_FAULT"], "| status", st()["status"]["state"], "| Critical:", [x["title"] for x in alerts() if x["tier"] == "Critical"])
ctl(fault=None); time.sleep(2)
ctl(link_up=False, physio="acute_event"); time.sleep(10)
print("outage ->", st()["status"]["state"], [(x["tier"], x["title"][:44]) for x in alerts() if x["type"] == "NO_DATA"])
ctl(link_up=True); t1 = time.time()
c = wait(lambda: [x for x in alerts() if x["key"] == "floor:red"], 25)
s = st(); print(f"reconnect: status={s['status']['state']} replay={s['status']['last_replay']['count'] if s['status']['last_replay'] else None}")
print(f"CRITICAL after {time.time()-t1:.1f}s:", c[0]["title"], c[0]["reasons"], "-> notified", c[0]["to"])
t2 = time.time()
c = wait(lambda: [x for x in alerts() if x["key"] == "floor:red" and x["level"] >= 1], 40)[0]
print(f"escalated after {time.time()-t2:.1f}s -> {c['to']}; notified chain {[n['who'] for n in c['notified']]}")
for step in ("ack", "respond", "resolve"):
    print(" ", step, "->", requests.post(B + f"/api/alerts/{c['id']}/{step}", json={"who": "Arun"}).json()["state"])
s = st(); print("metrics", s["metrics"]); print("ledger ", s["ledger"])
print("audit chain", requests.get(B + "/api/audit/verify").json())

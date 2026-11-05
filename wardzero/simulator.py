"""Simulated bedside device + gateway.

* Generates a reading every tick (1 tick = 15 simulated minutes, `speed` ticks per real second).
* STORE-AND-FORWARD: every reading goes into a local SQLite buffer first; the buffer is flushed (in order) whenever
  the link is up AND the API answers. If the network is cut (or the API is down) readings pile up and are replayed
  on reconnect. The server de-duplicates by (device_id, timestamp), so replays are safe.
* Scenario/fault state is read from the control endpoint (the dashboard is the remote control for the demo).
"""
import json, os, sqlite3, sys, time
from datetime import datetime
import requests
from . import config
from .synth import PatientSim

API = config.API_URL.rstrip("/")
BUF_PATH = os.getenv("WZ_BUFFER_PATH", "/tmp/wz_buffer.db")


class Buffer:
    def __init__(self, path=BUF_PATH):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS buf(seq INTEGER PRIMARY KEY, payload TEXT)")
        self.db.commit()

    def add(self, r):
        self.db.execute("INSERT OR REPLACE INTO buf VALUES (?,?)", (r["seq"], json.dumps(r))); self.db.commit()

    def all(self):
        return [json.loads(p) for (_, p) in self.db.execute("SELECT seq,payload FROM buf ORDER BY seq")]

    def drop_upto(self, seq):
        self.db.execute("DELETE FROM buf WHERE seq<=?", (seq,)); self.db.commit()

    def clear(self):
        self.db.execute("DELETE FROM buf"); self.db.commit()

    def __len__(self):
        return self.db.execute("SELECT COUNT(*) FROM buf").fetchone()[0]


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), "[device]", *a, flush=True)


def run():
    buf, sim, epoch = Buffer(), None, None
    ctrl = {"physio": "stable", "fault": None, "link_up": True, "power_loss": False, "speed": 4, "epoch": 0}
    log("starting; API =", API)
    while True:
        try:
            ctrl = requests.get(f"{API}/api/sim/control", timeout=2).json()
        except Exception:
            pass                                     # keep the last known scenario; device keeps working offline
        if ctrl["epoch"] != epoch and ctrl["epoch"] != 0:
            epoch = ctrl["epoch"]
            buf.clear()
            sim = PatientSim(seed=int(time.time()) % 10000, tick_min=config.TICK_MIN)
            seed = [sim.step("stable") for _ in range(config.CALIB_N)]
            try:
                requests.post(f"{API}/api/ingest", json={"epoch": epoch, "seed": True, "readings": seed}, timeout=30)
                log(f"epoch {epoch}: seeded {len(seed)} baseline readings (48 simulated hours of this patient's normal)")
            except Exception as e:
                log("seed failed, will retry on next epoch check:", e); epoch = None
            continue
        if sim is None:
            time.sleep(1); continue
        r = sim.step(ctrl["physio"], ctrl["fault"], ctrl["power_loss"])
        buf.add(r)
        if ctrl["link_up"]:
            pending = buf.all()
            try:
                resp = requests.post(f"{API}/api/ingest", json={"epoch": epoch, "readings": pending}, timeout=5)
                if resp.status_code == 200:
                    buf.drop_upto(pending[-1]["seq"])
                    if len(pending) > 1:
                        log(f"link restored: replayed {len(pending)} buffered readings in order ->", resp.json())
                elif resp.status_code == 409:
                    buf.clear()                      # stale epoch after a reset
            except Exception:
                if len(buf) % 20 == 1:
                    log(f"API unreachable, buffering locally ({len(buf)} readings)")
        elif len(buf) % 10 == 1:
            log(f"network down (simulated), buffering locally ({len(buf)} readings)")
        time.sleep(1.0 / max(1, min(16, ctrl.get("speed", 4))))


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)

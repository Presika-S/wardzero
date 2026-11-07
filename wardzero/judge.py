"""Judge Mode: a scripted, hands-free run of the full story for reviewers and for recording the demo video.
stable -> slow deterioration -> early Warning -> sensor-fault -> outage + buffering -> Critical siren ->
Caregiver 1 ignores -> escalates -> Caregiver 2 acknowledges -> resolve."""
import asyncio
import time


class JudgeRunner:
    def __init__(self, core):
        self.core, self.task, self.info = core, None, {"running": False, "step": 0, "total": 9, "caption": ""}

    def _say(self, step, caption):
        self.info = {"running": True, "step": step, "total": 9, "caption": caption}
        self.core.hub.emit({"type": "judge", **self.info})

    async def _wait(self, cond, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            await asyncio.sleep(0.25)
        return False

    def _open(self, key=None, tier=None):
        return [a for a in self.core.alerts.open_alerts() if (key is None or a["key"] == key) and (tier is None or a["tier"] == tier)]

    def start(self):
        self.stop()
        self.task = asyncio.get_running_loop().create_task(self._run())

    def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
        self.info = {"running": False, "step": 0, "total": 9, "caption": ""}
        self.core.hub.emit({"type": "judge", **self.info})

    async def _run(self):
        c = self.core
        try:
            c.reset(); c.set_control(speed=4)
            self._say(1, "Stable: the system has learned this patient's OWN normal (see the baseline bands).")
            await self._wait(lambda: c.last_rx is not None, 15); await asyncio.sleep(7)
            self._say(2, "Slow deterioration begins — no single value crosses a hospital threshold yet…")
            c.set_control(physio="slow_deterioration")
            await self._wait(lambda: self._open("risk:elevated"), 70)
            self._say(3, "Early WARNING with reasons: personal-baseline drift + trend, hours before any red value.")
            await asyncio.sleep(5)
            c.add_note("Amma is dizzy and not eating since morning / அம்மா சாப்பிடவில்லை, தலைசுற்றல்")
            self._say(4, "Caregiver note (English + Tamil) is read by the engine and shown in the explanation.")
            await asyncio.sleep(6)
            self._say(5, "Sensor fault: a loose probe is flagged as 'check sensor' — NOT a clinical alarm.")
            c.set_control(fault="probe_off"); await asyncio.sleep(6); c.set_control(fault=None)
            await asyncio.sleep(2)
            self._say(6, "Network outage: silence is not safety. NO DATA alert fires; the device buffers locally.")
            c.set_control(link_up=False, physio="acute_event")
            await asyncio.sleep(13)
            self._say(7, "Reconnect: buffered readings replay in order (idempotent) → Critical detected → SIREN.")
            c.set_control(link_up=True)
            await self._wait(lambda: self._open("floor:red", "Critical"), 25)
            self._say(8, "Caregiver 1 (Priya) does not respond… the system escalates to Caregiver 2 (Arun).")
            await self._wait(lambda: any(a["level"] >= 1 for a in self._open("floor:red")), 40)
            await asyncio.sleep(3)
            for a in self._open("floor:red"):
                c.alerts.ack(a["id"], "Arun")
            self._say(9, "Arun acknowledges → responding → resolved. Response times are logged in the audit trail.")
            await asyncio.sleep(3)
            for a in self._open():
                if a["tier"] != "Info":
                    c.alerts.respond(a["id"], "Arun")
            await asyncio.sleep(3)
            for a in self._open():
                if a["tier"] != "Info":
                    c.alerts.resolve(a["id"], "Arun")
            c.set_control(physio="stable")
            await asyncio.sleep(3)
            self.info = {"running": False, "step": 9, "total": 9, "caption": "Run complete. Press Judge Mode again to replay."}
            c.hub.emit({"type": "judge", **self.info})
        except asyncio.CancelledError:
            pass

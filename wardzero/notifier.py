"""Notification interface. Anything with .send(recipient, alert, level) works.
MockNotifier pushes a phone-style notification to the dashboard; NtfyNotifier sends a REAL push via ntfy
(optional, enabled by WZ_NTFY_URL)."""
import threading, time, urllib.request


class MockNotifier:
    def __init__(self, emit):
        self.emit = emit

    def send(self, rc, alert, level):
        self.emit({"type": "notification", "to": rc, "channel": "push", "level": level, "alert_id": alert["id"],
                   "tier": alert["tier"], "title": alert["title"],
                   "body": (alert["reasons"] or [""])[0], "wall": time.time()})


class NtfyNotifier:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")

    def send(self, rc, alert, level):
        def _go():
            try:
                req = urllib.request.Request(f"{self.base}/wardzero-{rc['id']}", data=(alert["reasons"] or [""])[0].encode(),
                    headers={"Title": f"[{alert['tier']}] {alert['title']}"[:200],
                             "Priority": "5" if alert["tier"] == "Critical" else "3", "Tags": "rotating_light"})
                urllib.request.urlopen(req, timeout=3).read()
            except Exception:
                pass          # a failed push must never break alerting
        threading.Thread(target=_go, daemon=True).start()

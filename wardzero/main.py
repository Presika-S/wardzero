"""FastAPI app: REST + WebSocket + static dashboard."""
import asyncio, json, os
from contextlib import asynccontextmanager
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from . import config
from .core import Core, StaleEpoch
from .judge import JudgeRunner

core: Core = None
WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


async def _loop():
    while True:
        try:
            core.heartbeat_tick()
            core.hub.emit({"type": "status", "status": core.status(), "metrics": core.alerts.metrics(),
                           "ledger": core.alerts.ledger, "checkins": core.checkins})
        except Exception as e:               # the monitor itself must never die silently
            print("monitor loop error:", e)
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app):
    global core
    core = Core()
    core.judge = JudgeRunner(core)
    app.state.core = core
    t = asyncio.create_task(_loop())
    yield
    t.cancel()


app = FastAPI(title="WardZero Core", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "monitor": "running", "epoch": core.control["epoch"]}


@app.get("/api/state")
async def state():
    return core.state()


@app.post("/api/ingest")
async def ingest(payload: dict = Body(...)):
    try:
        return core.ingest(payload)
    except StaleEpoch:
        return JSONResponse({"detail": "stale epoch"}, status_code=409)


@app.get("/api/sim/control")
async def get_control():
    return core.control


@app.post("/api/sim/control")
async def set_control(body: dict = Body(...)):
    return core.set_control(**body)


@app.post("/api/sim/reset")
async def reset():
    if core.judge:
        core.judge.stop()
    core.reset()
    return core.control


@app.post("/api/judge/start")
async def judge_start():
    core.judge.start()
    return {"started": True}


@app.post("/api/judge/stop")
async def judge_stop():
    core.judge.stop()
    return {"stopped": True}


@app.get("/api/alerts")
async def alerts():
    return core.alerts.list(100)


def _act(fn, aid, body):
    who = (body or {}).get("who", "Caregiver")
    try:
        return fn(aid, who)
    except KeyError:
        raise HTTPException(404, "alert not found")


@app.post("/api/alerts/{aid}/ack")
async def ack(aid: int, body: dict = Body(default={})):
    return _act(core.alerts.ack, aid, body)


@app.post("/api/alerts/{aid}/respond")
async def respond(aid: int, body: dict = Body(default={})):
    return _act(core.alerts.respond, aid, body)


@app.post("/api/alerts/{aid}/resolve")
async def resolve(aid: int, body: dict = Body(default={})):
    return _act(core.alerts.resolve, aid, body)


@app.post("/api/notes")
async def add_note(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "empty note")
    return core.add_note(text[:500], body.get("author", "Caregiver"))


@app.post("/api/caregivers/{cid}/checkin")
async def checkin(cid: str):
    core.checkin(cid)
    return {"ok": True}


@app.get("/api/audit")
async def audit(limit: int = 150):
    return core.audit.list(limit)


@app.get("/api/audit/verify")
async def audit_verify():
    return core.audit.verify()


@app.get("/api/model")
async def model():
    return core.model.card


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    q = asyncio.Queue()
    core.hub.queues.add(q)
    try:
        await sock.send_text(json.dumps({"type": "hello", "state": core.state()}, default=str))
        while True:
            await sock.send_text(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        core.hub.queues.discard(q)


@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB, "index.html"))


app.mount("/static", StaticFiles(directory=WEB), name="static")

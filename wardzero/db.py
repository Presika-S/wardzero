import os
from sqlalchemy import (create_engine, event, Column, Integer, Float, String, Boolean, Text, JSON,
                        UniqueConstraint)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Reading(Base):
    __tablename__ = "readings"
    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    seq = Column(Integer)
    ts = Column(String, index=True)                    # simulated (event) time, ISO
    temp = Column(Float); hr = Column(Float); sbp = Column(Float); dbp = Column(Float); spo2 = Column(Float)
    quality = Column(Float); battery = Column(Float); power = Column(String)
    valid = Column(Boolean, default=True); fault = Column(String, nullable=True)
    news2 = Column(Integer, nullable=True); risk_prob = Column(Float, nullable=True); risk_band = Column(String, nullable=True)
    received_wall = Column(Float)
    __table_args__ = (UniqueConstraint("device_id", "ts", name="uq_device_ts"),)   # idempotent ingestion


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    key = Column(String, index=True)
    type = Column(String)
    tier = Column(String)                               # Info | Warning | Critical
    title = Column(String)
    reasons = Column(JSON, default=list)
    state = Column(String, index=True)                  # INFO NOTIFIED ACKNOWLEDGED RESPONDING RESOLVED CLOSED
    sim_ts = Column(String)
    created_wall = Column(Float)
    level = Column(Integer, default=0)                  # 0 = Caregiver 1, 1 = Caregiver 2, 2 = Emergency contact
    deadline = Column(Float, nullable=True)
    notified = Column(JSON, default=list)
    escalations = Column(Integer, default=0)
    occurrences = Column(Integer, default=1)
    condition_active = Column(Boolean, default=True)
    acked_by = Column(String, nullable=True); acked_wall = Column(Float, nullable=True)
    responding_wall = Column(Float, nullable=True)
    resolved_by = Column(String, nullable=True); resolved_wall = Column(Float, nullable=True)
    closed_wall = Column(Float, nullable=True)


class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    wall = Column(Float)
    actor = Column(String); action = Column(String)
    alert_id = Column(Integer, nullable=True)
    detail = Column(Text, default="{}")
    prev = Column(String); hash = Column(String)


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    wall = Column(Float); sim_ts = Column(String)
    author = Column(String); text = Column(Text); lang = Column(String)
    flags = Column(JSON, default=list)


def make_session_factory(url):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        os.makedirs(os.path.dirname(url.replace("sqlite:///", "")) or ".", exist_ok=True)
    kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if ":memory:" in url:
        from sqlalchemy.pool import StaticPool
        kw["poolclass"] = StaticPool
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _p(dbapi, _):
            c = dbapi.cursor(); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=OFF"); c.close()
    Base.metadata.create_all(eng)
    return eng, sessionmaker(eng, expire_on_commit=False)

"""Central settings. Everything can be overridden with environment variables."""
import os

def _f(name, default): return float(os.getenv(name, default))
def _i(name, default): return int(os.getenv(name, default))

DB_URL = os.getenv("WZ_DB_URL", "sqlite:///./data/wardzero.db")   # Postgres-ready: postgresql+psycopg://...
MODEL_PATH = os.getenv("WZ_MODEL_PATH", "models/risk_model.joblib")
API_URL = os.getenv("WZ_API_URL", "http://localhost:8000")
NTFY_URL = os.getenv("WZ_NTFY_URL", "")          # e.g. http://ntfy:80  (optional real push)

TICK_MIN = 15                 # simulated minutes per reading (96 readings = 24 sim hours)
CALIB_N = 192                 # readings used to learn the personal baseline (48 sim hours)

# Alarm-fatigue controls (all illustrative defaults)
PERSIST_CRITICAL = _i("WZ_PERSIST_CRITICAL", 3)   # consecutive readings a red vital must persist
PERSIST_WARNING = _i("WZ_PERSIST_WARNING", 4)
PERSIST_RISK = _i("WZ_PERSIST_RISK", 6)
CLEAR_AFTER = _i("WZ_CLEAR_AFTER", 6)             # consecutive normal readings before a condition clears
COOLDOWN_S = _f("WZ_COOLDOWN_S", 20)              # wall-clock cooldown after a Warning/Info resolves
COOLDOWN_CRIT_S = _f("WZ_COOLDOWN_CRIT_S", 10)

# Escalation (wall-clock seconds; demo-short. A real deployment would use minutes.)
ACK_TIMEOUT_CRITICAL = _f("WZ_ACK_TIMEOUT_CRITICAL", 15)
ACK_TIMEOUT_WARNING = _f("WZ_ACK_TIMEOUT_WARNING", 45)

# Dead-man's switch: no data for this long raises a NO DATA alert
HEARTBEAT_S = _f("WZ_HEARTBEAT_S", 6)

# Risk bands on the model probability (illustrative)
BAND_MEDIUM = 0.30
BAND_HIGH = 0.65

CAREGIVERS = [
    {"id": "c1", "name": "Priya", "role": "Caregiver 1 (daughter)", "level": 0},
    {"id": "c2", "name": "Arun", "role": "Caregiver 2 (son)", "level": 1},
    {"id": "em", "name": "Dr. Meera", "role": "Emergency contact", "level": 2},
]
PATIENT = {"id": "p1", "name": "Lakshmi (synthetic)", "age": 68, "device_id": "bedside-01"}

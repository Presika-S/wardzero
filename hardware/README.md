# Hardware / IoT reference (example only)

> **Example, not a medical device.** This folder shows how a real bedside device would connect to Ward Zero. It has **not** been tested on real hardware, and the sensor reads are stubs returning simulated values until you replace them.

The Python stack in this repo uses a *software* bedside device (`wardzero/simulator.py`). A real device only has to do the same job: read vitals, keep them in a local buffer, and POST them in order to `/api/ingest`.

## Contents
- `esp32_wardzero_device/esp32_wardzero_device.ino` - ESP32 Arduino sketch with store-and-forward buffering and ordered replay.

## Suggested parts (example)
| Vital | Example sensor | Notes |
|---|---|---|
| Heart rate, SpO2 | MAX30102 (I2C) | finger/wrist PPG; motion causes artifacts, so report a signal `quality` |
| Skin / body temperature | DS18B20 or MAX30205 | skin temperature differs from core temperature |
| Blood pressure | External cuff monitor | cannot be measured by the patches above; the API requires `sbp`/`dbp`, so feed the last cuff value |
| Controller | ESP32 DevKit | Wi-Fi + I2C; BLE/Zigbee patches would send to a bedroom hub that forwards to the API |

Typical I2C wiring (MAX30102 to ESP32): VIN to 3V3, GND to GND, SDA to GPIO 21, SCL to GPIO 22.

## What the API expects
`POST http://<server>:8000/api/ingest` with JSON:

```json
{
  "seed": true,
  "readings": [
    {"device_id": "bedside-01", "seq": 1, "ts": "2026-11-05T06:30:00",
     "temp": 36.6, "hr": 74, "sbp": 122, "dbp": 76, "spo2": 97,
     "quality": 0.95, "battery": 100.0, "power": "mains"}
  ]
}
```
- Required fields: `device_id`, `ts` (ISO 8601), `temp`, `hr`, `sbp`, `dbp`, `spo2`. Optional: `seq`, `quality`, `battery`, `power` (`mains` or `battery`).
- The server is **idempotent by (`device_id`, `ts`)**: re-sending the same reading is safe, which is what makes replay after an outage work.
- Send several buffered readings in one request, oldest first.
- `"seed": true` marks readings used to learn the patient's personal baseline (the sketch does this for its first 192 readings; the simulator does the same with its first 48 simulated hours).
- Bad signals: send `spo2: 0` / `hr: 0` with low `quality` (probe off). The server's quality gate raises a "check sensor" notice, not a clinical alarm.
- If the device goes silent for 6 s (demo setting), the server flags the patient as **NO DATA - UNMONITORED**.

## Try the endpoint without any hardware
With the stack running (`docker compose up --build`):

```bash
curl -X POST http://localhost:8000/api/ingest -H "Content-Type: application/json" -d '{"readings":[{"device_id":"bedside-01","seq":1,"ts":"2026-11-05T06:30:00","temp":36.6,"hr":74,"sbp":122,"dbp":76,"spo2":97}]}'
```

## Known gaps in this example
- Buffer is in RAM only (a real device should persist to flash).
- Reading interval is 5 s for demos; real monitoring would sample every few minutes.
- No device authentication or TLS; a real deployment needs both.
- The server's baseline logic expects an initial calibration set; with a real patient you would collect it first.

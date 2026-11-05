/*
 * Ward Zero - EXAMPLE bedside device firmware (ESP32 + Arduino core)
 *
 * !! EXAMPLE / REFERENCE ONLY !!  Not a medical device. Not clinically validated. Not tested on real hardware.
 * It shows how a real device would plug into the same /api/ingest endpoint that wardzero/simulator.py uses.
 *
 * What it does (same behaviour as the Python simulator):
 *   1. Reads HR, SpO2, temperature (and BP from an external cuff, if you have one) once per SAMPLE_MS.
 *   2. Puts every reading in a local buffer FIRST (store-and-forward).
 *   3. When Wi-Fi + API are reachable, sends the buffered readings IN ORDER, then drops them.
 *      The server de-duplicates by (device_id, ts), so a replay after an outage is safe.
 *   4. Reports signal quality, battery % and power source so the server can gate bad readings
 *      (probe off -> quality low / impossible values -> "check sensor" notice, not a clinical alarm).
 *
 * Libraries (Arduino Library Manager): ArduinoJson (v7), and for real sensors e.g. SparkFun MAX3010x (MAX30102)
 * and DallasTemperature/OneWire (DS18B20) or a MAX30205 library. Board: "ESP32 Dev Module".
 *
 * Sensor reads below are STUBS returning simulated numbers (USE_SIMULATED_SENSORS = 1) so the sketch compiles and
 * the pipeline can be tried without sensors. Replace the three read functions with real driver calls.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ---------- configuration ----------
const char* WIFI_SSID   = "YOUR_WIFI_NAME";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";
const char* API_URL     = "http://192.168.1.50:8000/api/ingest";   // your Ward Zero API (docker compose up)
const char* DEVICE_ID   = "bedside-01";
const uint32_t SAMPLE_MS = 5000;        // 1 reading every 5 s for a demo (real use: every few minutes)
const int  BUF_MAX       = 200;         // in-RAM buffer; a real device would also persist to flash (LittleFS)
const int  SEED_COUNT    = 192;         // first N readings are sent with "seed":true so the server learns this patient's baseline
#define USE_SIMULATED_SENSORS 1

// ---------- reading buffer (ring) ----------
struct Reading {
  uint32_t seq; time_t ts;
  float temp, hr, sbp, dbp, spo2, quality, battery; bool onMains;
};
Reading buf[BUF_MAX];
int head = 0, count = 0;                // oldest item at head
uint32_t seqNo = 0, sentTotal = 0;

void bufPush(const Reading& r) {
  if (count == BUF_MAX) { head = (head + 1) % BUF_MAX; count--; }   // overwrite oldest if the outage is very long
  buf[(head + count) % BUF_MAX] = r; count++;
}

// ---------- sensors (REPLACE THESE STUBS) ----------
// Returns false if the probe is off / no finger detected.
bool readSpO2HR(float& spo2, float& hr, float& quality) {
#if USE_SIMULATED_SENSORS
  spo2 = 96.5 + (random(-10, 11) / 10.0); hr = 74 + random(-4, 5); quality = 0.95; return true;
#else
  // TODO: MAX30102 -> compute SpO2/HR from red/IR samples (SparkFun library example "Example8_SPO2").
  //       Set quality from signal amplitude / finger-detected flag. Return false when no finger is detected.
  return false;
#endif
}
bool readTemperature(float& tempC) {
#if USE_SIMULATED_SENSORS
  tempC = 36.6 + (random(-3, 4) / 10.0); return true;
#else
  // TODO: DS18B20 / MAX30205 skin or axillary temperature in deg C.
  return false;
#endif
}
bool readBloodPressure(float& sys, float& dia) {
#if USE_SIMULATED_SENSORS
  sys = 122 + random(-4, 5); dia = 76 + random(-3, 4); return true;
#else
  // Blood pressure cannot be measured by these patches. Take it from an external cuff (BLE/serial) or a manual entry.
  // TODO: read the last cuff value. The server requires sbp/dbp fields.
  return false;
#endif
}
float readBatteryPercent() { return 100.0; /* TODO: ADC on a battery divider / fuel gauge */ }
bool  onMainsPower()       { return true;   /* TODO: sense the charger pin */ }

// ---------- helpers ----------
void isoTime(time_t t, char* out, size_t n) { struct tm tmv; gmtime_r(&t, &tmv); strftime(out, n, "%Y-%m-%dT%H:%M:%S", &tmv); }

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) delay(200);
}

void takeReading() {
  Reading r; r.seq = ++seqNo; r.ts = time(nullptr);
  float spo2 = 0, hr = 0, q = 0.15, temp = 0, sbp = 0, dbp = 0;
  bool ok = readSpO2HR(spo2, hr, q);
  if (!ok) { spo2 = 0; hr = 0; q = 0.15; }          // probe off: the server's quality gate turns this into a "check probe" notice
  if (!readTemperature(temp)) temp = 0;
  if (!readBloodPressure(sbp, dbp)) { sbp = 0; dbp = 0; }
  r.temp = temp; r.hr = hr; r.sbp = sbp; r.dbp = dbp; r.spo2 = spo2; r.quality = q;
  r.battery = readBatteryPercent(); r.onMains = onMainsPower();
  bufPush(r);
}

// Send everything in the buffer, oldest first. Drop items only after the server answered 200.
void flushBuffer() {
  if (count == 0 || WiFi.status() != WL_CONNECTED) return;
  JsonDocument doc;
  bool seeding = sentTotal < (uint32_t)SEED_COUNT;
  if (seeding) doc["seed"] = true;
  JsonArray arr = doc["readings"].to<JsonArray>();
  for (int i = 0; i < count; i++) {
    const Reading& r = buf[(head + i) % BUF_MAX];
    char ts[24]; isoTime(r.ts, ts, sizeof ts);
    JsonObject o = arr.add<JsonObject>();
    o["device_id"] = DEVICE_ID; o["seq"] = r.seq; o["ts"] = ts;
    o["temp"] = r.temp; o["hr"] = r.hr; o["sbp"] = r.sbp; o["dbp"] = r.dbp; o["spo2"] = r.spo2;
    o["quality"] = r.quality; o["battery"] = r.battery; o["power"] = r.onMains ? "mains" : "battery";
  }
  String body; serializeJson(doc, body);
  HTTPClient http; http.begin(API_URL); http.addHeader("Content-Type", "application/json"); http.setTimeout(5000);
  int code = http.POST(body); http.end();
  if (code == 200) { sentTotal += count; head = 0; count = 0; Serial.printf("sent %d readings\n", (int)arr.size()); }
  else Serial.printf("API not reachable (code %d), keeping %d readings buffered\n", code, count);
}

void setup() {
  Serial.begin(115200);
  connectWifi();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");   // timestamps in UTC; the server orders and de-duplicates by ts
  Serial.println("Ward Zero example device started");
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last >= SAMPLE_MS) {
    last = millis();
    connectWifi();
    takeReading();      // always buffer first
    flushBuffer();      // then try to send; on failure readings stay buffered and replay in order later
  }
}

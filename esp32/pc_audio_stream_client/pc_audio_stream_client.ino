/*
 * STADIUMGUARD - ESP32 FINAL
 * - Pas d'ESP-CAM (camera du PC uniquement)
 * - Pas de servo
 * - Capteurs traités localement par ESP32
 * - IA du PC consultée via Wi-Fi
 * - Mode offline automatique si Wi-Fi coupé
 * - LCD I2C : SDA=26 / SCL=27
 * - Speaker : GPIO33 (PWM 8-bit)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ------------------ RESEAU ------------------
const char* WIFI_SSID = "Wydad";
const char* WIFI_PASS = "partager";
const char* BACKEND_HOST = "192.168.137.1";  // IP LAN du PC
const int   BACKEND_PORT = 5000;
const char* DEVICE_ID = "esp32-robot-A1";

// ------------------ PINS (conformes à ton projet) ------------------
#define PIN_SON       34   // Micro analogique
#define PIN_GAZ       32   // Capteur gaz analogique
#define PIN_PIR       35   // Mouvement digital
#define PIN_OBSTACLE  13   // Capteur obstacle digital (LOW = obstacle)
#define PIN_SPEAKER   33   // Haut-parleur / baffle via PWM
#define PIN_TX_NANO   25   // Optionnel: vers carte moteur (F/S)

// LCD I2C
#define LCD_SDA       26
#define LCD_SCL       27
LiquidCrystal_I2C lcd(0x27, 16, 2);

// PWM audio (sortie sur PIN_SPEAKER)
const int SPEAKER_CH = 0;
const int SPEAKER_BASE_FREQ = 16000;
const int SPEAKER_RES_BITS = 8;

// ------------------ SEUILS & TEMPS ------------------
const int THRESH_GAZ_DANGER_FALLBACK = 2500;
const int THRESH_SON_LOCAL_ALERT_FALLBACK = 1800;
const unsigned long CALIBRATION_MS = 3000;
const unsigned long SENSOR_LOOP_MS = 120;
const unsigned long ALERT_POLL_MS = 1500;
const unsigned long SEND_AUDIO_MS = 500;
const unsigned long SEND_GAS_MS = 1000;

const unsigned long COOLDOWN_OBSTACLE_MS = 3500;
const unsigned long COOLDOWN_GAZ_MS = 2000;
const unsigned long COOLDOWN_IA_MS = 5000;
const unsigned long SOUND_TRIGGER_HOLD_MS = 350;
const bool SHOW_CALIBRATION_LCD = false; // true si tu veux voir "CALIBRATION..." sur LCD

unsigned long lastSensorLoop = 0;
unsigned long lastAlertPoll = 0;
unsigned long lastAudioSend = 0;
unsigned long lastGasSend = 0;
unsigned long lastObstaclePlay = 0;
unsigned long lastGasPlay = 0;
unsigned long lastAiPlay = 0;

bool wifiOnline = false;
bool welcomePlayed = false;
int lastAiLevel = 0;  // 0=LOW,1=MEDIUM,2=HIGH/CRITICAL

// Seuils dynamiques après calibration
float baselineGas = 0.0f;
float baselineSound = 0.0f;
float gasEnterThreshold = THRESH_GAZ_DANGER_FALLBACK;
float gasExitThreshold = THRESH_GAZ_DANGER_FALLBACK - 200.0f;
float soundEnterThreshold = THRESH_SON_LOCAL_ALERT_FALLBACK;
float soundExitThreshold = THRESH_SON_LOCAL_ALERT_FALLBACK - 250.0f;

// Etats pour hystérésis (évite oscillations autour du seuil)
bool gasAlarmActive = false;
bool localSoundAlarmActive = false;
unsigned long soundAboveSinceMs = 0;
unsigned long lastDebugPrint = 0;
float audioNormEma = 0.0f;

// ------------------ COMPAT PWM ESP32 ------------------
// ESP32 core 2.x: ledcSetup/ledcAttachPin/ledcWrite(channel,...)
// ESP32 core 3.x: ledcAttach/ledcWrite(pin,...)
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  #define USE_NEW_LEDC_API 1
#else
  #define USE_NEW_LEDC_API 0
#endif

void speakerPwmBegin() {
#if USE_NEW_LEDC_API
  ledcAttach(PIN_SPEAKER, SPEAKER_BASE_FREQ, SPEAKER_RES_BITS);
#else
  ledcSetup(SPEAKER_CH, SPEAKER_BASE_FREQ, SPEAKER_RES_BITS);
  ledcAttachPin(PIN_SPEAKER, SPEAKER_CH);
#endif
}

void speakerWriteDuty(uint8_t duty) {
#if USE_NEW_LEDC_API
  ledcWrite(PIN_SPEAKER, duty);
#else
  ledcWrite(SPEAKER_CH, duty);
#endif
}

void speakerWriteToneHz(int freqHz) {
#if USE_NEW_LEDC_API
  ledcWriteTone(PIN_SPEAKER, freqHz);
#else
  ledcWriteTone(SPEAKER_CH, freqHz);
#endif
}

// ------------------ HELPERS ------------------
String baseUrl() {
  return String("http://") + BACKEND_HOST + ":" + BACKEND_PORT;
}

String extractJsonStringValue(const String& json, const String& key) {
  String needle = "\"" + key + "\"";
  int k = json.indexOf(needle);
  if (k < 0) return "";

  int colon = json.indexOf(':', k + needle.length());
  if (colon < 0) return "";

  int i = colon + 1;
  while (i < json.length() && (json[i] == ' ' || json[i] == '\t' || json[i] == '\r' || json[i] == '\n')) i++;
  if (i >= json.length() || json[i] != '\"') return "";

  int start = i + 1;
  int end = json.indexOf('\"', start);
  if (end < 0) return "";
  return json.substring(start, end);
}

void lcdShow(const String& line1, const String& line2) {
  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));
}

void sendMoveCommand(char c) {
  // Optionnel: conserve la logique existante avec carte moteur
  // 'F' = avance/patrouille, 'S' = stop
  Serial2.print(c);
}

void playLocalBeep(int freqHz, int ms) {
  speakerWriteToneHz(freqHz);
  delay(ms);
  speakerWriteToneHz(0);
}

void playPatternWelcome() {
  playLocalBeep(900, 120);
  delay(60);
  playLocalBeep(1200, 140);
}

void playPatternObstacle() {
  playLocalBeep(1200, 140);
  delay(70);
  playLocalBeep(1200, 140);
}

void playPatternGas() {
  playLocalBeep(1800, 180);
  delay(80);
  playLocalBeep(1800, 180);
  delay(80);
  playLocalBeep(1800, 180);
}

void playPatternIncident() {
  playLocalBeep(1500, 180);
  delay(90);
  playLocalBeep(1300, 180);
}

bool playEventOrFallback(const String& eventName, void (*fallbackFn)()) {
  Serial.printf("EVENT %s\n", eventName.c_str());
  if (wifiOnline) {
    if (playEventFromPc(eventName)) {
      Serial.printf("EVENT %s AUDIO_STREAM OK\n", eventName.c_str());
      return true;
    }
    Serial.printf("EVENT %s AUDIO_STREAM FALLBACK\n", eventName.c_str());
  } else {
    Serial.printf("EVENT %s OFFLINE FALLBACK\n", eventName.c_str());
  }
  if (fallbackFn) fallbackFn();
  return false;
}

bool cooldownOk(unsigned long nowMs, const String& type) {
  if (type == "obstacle") return (nowMs - lastObstaclePlay) >= COOLDOWN_OBSTACLE_MS;
  if (type == "gas") return (nowMs - lastGasPlay) >= COOLDOWN_GAZ_MS;
  if (type == "ia") return (nowMs - lastAiPlay) >= COOLDOWN_IA_MS;
  return true;
}

void markPlayed(unsigned long nowMs, const String& type) {
  if (type == "obstacle") lastObstaclePlay = nowMs;
  else if (type == "gas") lastGasPlay = nowMs;
  else if (type == "ia") lastAiPlay = nowMs;
}

// ------------------ WIFI ------------------
bool connectWiFiOnce(unsigned long timeoutMs) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < timeoutMs) {
    delay(250);
  }
  return WiFi.status() == WL_CONNECTED;
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiOnline = true;
    return;
  }
  wifiOnline = false;
  WiFi.disconnect(true);
  delay(150);
  wifiOnline = connectWiFiOnce(2500); // tentative courte non bloquante
}

// ------------------ AUDIO PC -> ESP32 ------------------
bool parseWavHeader(const uint8_t* h, size_t len, uint32_t& sampleRate, uint16_t& channels, uint16_t& bitsPerSample) {
  if (len < 44) return false;
  if (!(h[0] == 'R' && h[1] == 'I' && h[2] == 'F' && h[3] == 'F')) return false;
  if (!(h[8] == 'W' && h[9] == 'A' && h[10] == 'V' && h[11] == 'E')) return false;
  uint16_t audioFormat = (uint16_t)(h[20] | (h[21] << 8));
  channels = (uint16_t)(h[22] | (h[23] << 8));
  sampleRate = (uint32_t)(h[24] | (h[25] << 8) | (h[26] << 16) | (h[27] << 24));
  bitsPerSample = (uint16_t)(h[34] | (h[35] << 8));
  return audioFormat == 1;  // PCM
}

size_t readExactBytesWithTimeout(WiFiClient* stream, uint8_t* dst, size_t want, unsigned long timeoutMs) {
  size_t total = 0;
  unsigned long t0 = millis();
  while (total < want && (millis() - t0) < timeoutMs) {
    int avail = stream->available();
    if (avail <= 0) {
      delay(1);
      continue;
    }
    int toRead = min((int)(want - total), avail);
    int n = stream->readBytes(dst + total, toRead);
    if (n > 0) total += (size_t)n;
  }
  return total;
}

bool playEventFromPc(const String& eventName) {
  if (!wifiOnline) return false;

  HTTPClient http;
  String url = baseUrl() + "/api/robot/audio-stream?event=" + eventName;
  http.setTimeout(12000);
  http.begin(url);

  int code = http.GET();
  if (code != 200) {
    Serial.printf("AUDIO_STREAM FAIL event=%s http=%d url=%s\n",
                  eventName.c_str(), code, url.c_str());
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  uint8_t header[44];
  size_t got = readExactBytesWithTimeout(stream, header, sizeof(header), 2500);
  uint32_t sr = 0;
  uint16_t ch = 0;
  uint16_t bits = 0;

  if (!parseWavHeader(header, got, sr, ch, bits) || !(ch == 1 && bits == 8 && sr == 16000)) {
    Serial.printf("AUDIO_STREAM BAD_WAV event=%s got=%u sr=%lu ch=%u bits=%u (need 16000/mono/8bit PCM)\n",
                  eventName.c_str(), (unsigned)got, (unsigned long)sr, (unsigned)ch, (unsigned)bits);
    http.end();
    return false;
  }

  const unsigned int usPerSample = 1000000UL / sr;
  uint8_t buffer[256];

  while (http.connected() || stream->available()) {
    int avail = stream->available();
    if (avail <= 0) {
      delay(1);
      continue;
    }
    int n = stream->readBytes(buffer, min((int)sizeof(buffer), avail));
    for (int i = 0; i < n; i++) {
      speakerWriteDuty(buffer[i]); // PWM 8-bit sur PIN_SPEAKER
      delayMicroseconds(usPerSample);
    }
  }

  speakerWriteDuty(127);
  http.end();
  return true;
}

// ------------------ CAPTEURS ------------------
float readGasRaw() {
  return (float)analogRead(PIN_GAZ);  // 0..4095
}

float readSoundRaw() {
  return (float)analogRead(PIN_SON);  // 0..4095
}

float readSoundPeakRaw() {
  // Capture un pic court (clap/impact) pour éviter de rater le son
  // avec un seul échantillon toutes les 120 ms.
  float peak = 0.0f;
  for (int i = 0; i < 24; i++) {
    float v = (float)analogRead(PIN_SON);
    if (v > peak) peak = v;
    delayMicroseconds(800);
  }
  return peak;
}

bool readMotion() {
  return digitalRead(PIN_PIR) == HIGH;
}

bool readObstacle() {
  return digitalRead(PIN_OBSTACLE) == LOW; // convention capteur obstacle
}

void calibrateSensors() {
  if (SHOW_CALIBRATION_LCD) {
    lcdShow("CALIBRATION...", "NE PAS BOUGER");
  }
  unsigned long startMs = millis();
  uint32_t count = 0;
  double gasSum = 0.0;
  double soundSum = 0.0;

  while (millis() - startMs < CALIBRATION_MS) {
    gasSum += readGasRaw();
    soundSum += readSoundRaw();
    count++;
    delay(20);
  }

  if (count == 0) {
    baselineGas = THRESH_GAZ_DANGER_FALLBACK - 400.0f;
    baselineSound = THRESH_SON_LOCAL_ALERT_FALLBACK - 400.0f;
  } else {
    baselineGas = (float)(gasSum / count);
    baselineSound = (float)(soundSum / count);
  }

  // Marges empiriques (terrain) + bornes minimales de sécurité
  gasEnterThreshold = max((float)(baselineGas + 700.0f), (float)THRESH_GAZ_DANGER_FALLBACK);
  gasExitThreshold = gasEnterThreshold - 220.0f;

  // Seuil son moins sensible + hysteresis plus large pour éviter les faux positifs.
  soundEnterThreshold = max((float)(baselineSound + 220.0f), 1850.0f);
  soundExitThreshold = soundEnterThreshold - 140.0f;

  Serial.printf("Calibration done | gas base=%.1f enter=%.1f exit=%.1f\n",
                baselineGas, gasEnterThreshold, gasExitThreshold);
  Serial.printf("Calibration done | snd base=%.1f enter=%.1f exit=%.1f\n",
                baselineSound, soundEnterThreshold, soundExitThreshold);
}

bool isGasDanger(float gasRaw) {
  if (!gasAlarmActive && gasRaw >= gasEnterThreshold) {
    gasAlarmActive = true;
  } else if (gasAlarmActive && gasRaw <= gasExitThreshold) {
    gasAlarmActive = false;
  }
  return gasAlarmActive;
}

bool isLocalSoundDanger(float soundRaw, bool motion) {
  // Si PIR actif on baisse un peu le seuil, mais moins agressivement qu'avant.
  float enterThreshold = motion ? (soundEnterThreshold * 0.90f) : soundEnterThreshold;
  float exitThreshold = motion ? (soundExitThreshold * 0.90f) : soundExitThreshold;
  unsigned long nowMs = millis();

  if (!localSoundAlarmActive) {
    if (soundRaw >= enterThreshold) {
      if (soundAboveSinceMs == 0) {
        soundAboveSinceMs = nowMs;
      } else if ((nowMs - soundAboveSinceMs) >= SOUND_TRIGGER_HOLD_MS) {
        localSoundAlarmActive = true;
      }
    } else {
      soundAboveSinceMs = 0;
    }
  } else if (soundRaw <= exitThreshold) {
    localSoundAlarmActive = false;
    soundAboveSinceMs = 0;
  }

  return localSoundAlarmActive;
}

// ------------------ PRETRAITEMENT AUDIO LOCAL ------------------
void computeSimpleAudioFeatures(float soundRaw, float& rms, float& centroidHz, float& zcr, String& label, float& conf) {
  // Sans I2S ici (micro analogique), on estime des features simplifiées
  // pour rester compatible avec l'API backend.
  // IMPORTANT: on normalise par rapport au baseline calibré pour éviter
  // d'étiqueter "bagarre" dès le démarrage en environnement bruyant.
  float noiseFloor = baselineSound;
  float dangerRef = max(soundEnterThreshold, noiseFloor + 1.0f);
  float span = max(dangerRef - noiseFloor, 120.0f);
  float norm = (soundRaw - noiseFloor) / span;   // 0.0 ~ bruit normal, 1.0 ~ zone alerte locale
  norm = constrain(norm, 0.0f, 2.0f);

  // Lissage léger pour stabiliser l'étiquette audio envoyée au backend.
  audioNormEma = 0.25f * norm + 0.75f * audioNormEma;

  rms = constrain(audioNormEma, 0.0f, 1.0f);
  centroidHz = 300.0f + rms * 3000.0f;
  zcr = 0.05f + rms * 0.4f;

  // Profil conservateur: on reste en classes calmes tant que le niveau
  // ne dépasse pas clairement la zone de bruit ambiant calibrée.
  if (rms < 0.35f) {
    label = "silence";
    conf = 0.85f;
  } else if (rms < 0.78f) {
    label = "chants supportaires";
    conf = 0.74f;
  } else if (rms < 0.96f) {
    label = "bagarre";
    conf = 0.76f;
  } else {
    label = "bombes";
    conf = 0.80f;
  }
}

// ------------------ ENVOI VERS BACKEND ------------------
void postAudio(float soundRaw) {
  if (!wifiOnline) return;
  float rms, centroidHz, zcr, conf;
  String label;
  computeSimpleAudioFeatures(soundRaw, rms, centroidHz, zcr, label, conf);

  HTTPClient http;
  String url = baseUrl() + "/api/esp32/audio";
  String body = String("{\"device_id\":\"") + DEVICE_ID +
                "\",\"timestamp\":" + String(millis() / 1000.0f, 3) +
                ",\"audio\":{\"label\":\"" + label +
                "\",\"confidence\":" + String(conf, 2) +
                ",\"rms\":" + String(rms, 4) +
                ",\"centroid_hz\":" + String(centroidHz, 1) +
                ",\"zcr\":" + String(zcr, 4) + "}}";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  if (code < 200 || code >= 300) {
    Serial.printf("POST_AUDIO FAIL http=%d url=%s\n", code, url.c_str());
  }
  http.end();
}

void postGas(float gasRaw) {
  if (!wifiOnline) return;
  bool detected = isGasDanger(gasRaw);
  HTTPClient http;
  String url = baseUrl() + "/api/esp32/gas";
  String body = String("{\"device_id\":\"") + DEVICE_ID +
                "\",\"timestamp\":" + String(millis() / 1000.0f, 3) +
                ",\"gas\":{\"sensor_ppm\":" + String(gasRaw, 1) +
                ",\"detected\":" + (detected ? "true" : "false") +
                ",\"confidence\":0.80}}";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  if (code < 200 || code >= 300) {
    Serial.printf("POST_GAS FAIL http=%d url=%s\n", code, url.c_str());
  }
  http.end();
}

int pollAiAlertLevel() {
  if (!wifiOnline) return 0;
  HTTPClient http;
  String url = baseUrl() + "/api/alert";
  http.setTimeout(3000);
  http.begin(url);
  int code = http.GET();
  if (code != 200) {
    http.end();
    return 0;
  }
  String payload = http.getString();
  http.end();

  String level = extractJsonStringValue(payload, "level");
  level.toUpperCase();
  if (level == "CRITICAL" || level == "HIGH") return 2;
  if (level == "MEDIUM") return 1;
  return 0;
}

// ------------------ LOGIQUE DECISION ------------------
void handleDangerGas(unsigned long nowMs) {
  sendMoveCommand('S');
  lcdShow("ALERTE", "");
  if (cooldownOk(nowMs, "gas")) {
    playEventOrFallback("gas_emergency", playPatternGas);
    markPlayed(nowMs, "gas");
  }
}

void handleObstacle(unsigned long nowMs) {
  sendMoveCommand('S');
  lcdShow("ATTENTION", "");
  if (cooldownOk(nowMs, "obstacle")) {
    playEventOrFallback("obstacle", playPatternObstacle);
    markPlayed(nowMs, "obstacle");
  }
}

void handleAiAlert(unsigned long nowMs) {
  sendMoveCommand('S');
  lcdShow("INCIDENT", "");
  if (cooldownOk(nowMs, "ia")) {
    playEventOrFallback("ai_alert", playPatternIncident);
    markPlayed(nowMs, "ia");
  }
}

void handlePatrolOnline() {
  sendMoveCommand('F');
  lcdShow("PATROUILLE WIFI", "IA CONNECTEE");
}

void handlePatrolOffline() {
  sendMoveCommand('F');
  lcdShow("MODE OFFLINE", "SENSORS ONLY");
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, 16, PIN_TX_NANO);

  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_OBSTACLE, INPUT);
  analogReadResolution(12);

  // LCD
  Wire.begin(LCD_SDA, LCD_SCL);
  lcd.init();
  lcd.backlight();
  lcdShow("STADIUM GUARD", "BOOTING...");

  // Speaker PWM
  speakerPwmBegin();
  speakerWriteDuty(127);

  // Calibration capteurs au boot (zone supposée calme)
  calibrateSensors();

  wifiOnline = connectWiFiOnce(8000);
  if (wifiOnline) {
    lcdShow("WIFI CONNECTE", WiFi.localIP().toString());
  } else {
    lcdShow("WIFI OFFLINE", "MODE LOCAL");
  }
  delay(700);

  if (!welcomePlayed) {
    lcdShow("BIENVENUE", "");
    // Essaie le son du PC si possible, sinon beep local (fallback automatique).
    playEventOrFallback("welcome", playPatternWelcome);
    delay(900); // laisse le message visible avant la logique de patrouille/alertes
  }
  welcomePlayed = true;
}

void loop() {
  unsigned long now = millis();
  ensureWiFi();

  if (now - lastSensorLoop < SENSOR_LOOP_MS) return;
  lastSensorLoop = now;

  // 1) Lire capteurs locaux
  float gasRaw = readGasRaw();
  float soundRaw = readSoundPeakRaw();
  bool motion = readMotion();
  bool obstacle = readObstacle();

  // Debug capteurs (utile pour ajuster sensibilité en test terrain)
  if (now - lastDebugPrint >= 1000) {
    lastDebugPrint = now;
    Serial.printf("DBG wifi=%d gas=%.0f(g>=%.0f) snd=%.0f(s>=%.0f) pir=%d obs=%d\n",
                  wifiOnline ? 1 : 0,
                  gasRaw, gasEnterThreshold,
                  soundRaw, soundEnterThreshold,
                  motion ? 1 : 0, obstacle ? 1 : 0);
  }

  // 2) Envoyer vers PC quand Wi-Fi dispo
  if (wifiOnline) {
    if (now - lastAudioSend >= SEND_AUDIO_MS) {
      lastAudioSend = now;
      postAudio(soundRaw);
    }
    if (now - lastGasSend >= SEND_GAS_MS) {
      lastGasSend = now;
      postGas(gasRaw);
    }
  }

  // 3) Priorité sécurité locale (toujours active même offline)
  if (obstacle) {
    handleObstacle(now);
    return;
  }
  if (isGasDanger(gasRaw)) {
    handleDangerGas(now);
    return;
  }

  // Réaction locale au son en online ET offline.
  if (isLocalSoundDanger(soundRaw, motion)) {
    sendMoveCommand('S');
    lcdShow("ALERTE SON", "VERIFICATION");
    playPatternIncident();
    return;
  }

  // 4) IA en ligne + fallback local si offline
  if (wifiOnline) {
    if (now - lastAlertPoll >= ALERT_POLL_MS) {
      lastAlertPoll = now;
      lastAiLevel = pollAiAlertLevel();
    }

    if (lastAiLevel >= 2) {
      handleAiAlert(now);
      return;
    }

    // IA low/medium -> patrouille
    handlePatrolOnline();
  } else {
    handlePatrolOffline();
  }
}

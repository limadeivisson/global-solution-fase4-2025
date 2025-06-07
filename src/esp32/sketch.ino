/**
 * @file sketch.ino
 * @brief Sistema FloodSentry AI para monitoramento de níveis de água e chuva.
 * Publica dados e ESTADO de alerta crítico local via MQTT.
 * Recebe comandos de alerta do sistema.
 * Categorias de chuva refinadas.
 * @author OmarAssem (Originalmente FloodSentryAI)
 * @date 01/06/2025 (Data da refatoração)
 */

// Bibliotecas
#include <WiFi.h>
#include <PubSubClient.h>

// Definições dos Pinos
const int TRIG_PIN        = 12; 
const int ECHO_PIN        = 14; 
const int RAIN_BUTTON_PIN = 27; 
const int LED_MQTT_PIN    = 2;  
const int LED_RAIN_PIN    = 4;  
const int LED_WATER_PIN   = 16; 
const int LED_RISK_PIN    = 17; 

// Configuração do Wi-Fi
const char* SSID        = "Wokwi-GUEST"; 
const char* PASSWORD    = "";            

// Configuração do Broker MQTT
const char* MQTT_BROKER      = "test.mosquitto.org"; 
const int   MQTT_PORT        = 1883;                 
const char* MQTT_CLIENT_ID   = "FloodSentryESP32_OmarAssem_StatefulCrit_V3"; // ID Atualizado

// Tópicos MQTT
const char* MQTT_TOPIC_WATER_LEVEL        = "fiap/gs/OmarAssem/flood_sentry/sensor/water_level";
const char* MQTT_TOPIC_RAINFALL           = "fiap/gs/OmarAssem/flood_sentry/sensor/rainfall";
const char* MQTT_TOPIC_COMMAND            = "fiap/gs/OmarAssem/flood_sentry/command/alert_status"; 
const char* MQTT_TOPIC_CRITICAL_ALERT_STATUS = "fiap/gs/OmarAssem/flood_sentry/alert/critical_status"; // Tópico para estado do alerta crítico

// Limiares e Temporizações
const float WATER_LEVEL_HIGH_THRESHOLD_CM     = 50.0f;  
const float WATER_LEVEL_MEDIUM_THRESHOLD_CM   = 150.0f; 
const float CRITICAL_DISTANCE_THRESHOLD_CM    = 10.0f;  
const int   RAINFALL_HEAVY_THRESHOLD          = 10;     // A partir de 10 = Pesada
const int   RAINFALL_MODERATE_THRESHOLD       = 5;      // A partir de 5 (até 9) = Moderada
// Chuva leve será de 1 até (RAINFALL_MODERATE_THRESHOLD - 1)

const unsigned long DEBOUNCE_DELAY_MS                   = 50;    
const unsigned long RAIN_LED_FLASH_DURATION_MS          = 150;   
const unsigned long WATER_LED_BLINK_INTERVAL_MS         = 500;   
const unsigned long RAIN_LED_HEAVY_BLINK_INTERVAL_MS    = 200;   
const unsigned long MQTT_PUBLISH_INTERVAL_MS            = 10000; 
const unsigned long MQTT_RECONNECT_RETRY_MS             = 5000;  
const unsigned long MQTT_LED_RECONNECT_BLINK_INTERVAL_MS= 500;   
const unsigned long WIFI_CONNECT_TIMEOUT_MS               = 20000; 
const unsigned long WIFI_LED_CONNECT_BLINK_INTERVAL_MS  = 250;   
const unsigned long MAIN_LOOP_DELAY_MS                  = 50;    
const unsigned long HCSR04_PULSE_TIMEOUT_US             = 50000UL; 

WiFiClient espClient;
PubSubClient mqttClient(espClient);

int  accumulatedRainfall = 0;
bool rainButtonPressedState = false;
bool lastDebouncedRainButtonState = false;
unsigned long lastRainButtonPressTime = 0;
unsigned long rainLedFlashEndTime = 0;
unsigned long waterLedBlinkPreviousMillis = 0;
bool waterLedState = LOW;
unsigned long rainLedHeavyBlinkPreviousMillis = 0;
bool rainLedHeavyState = LOW;
unsigned long mqttLedBlinkPreviousMillis = 0;
unsigned long lastMqttPublishTime = 0;
bool mqtt_high_risk_active = false; 
bool esp32_critical_alert_is_currently_active = false; // Rastreia o estado do alerta crítico local

// --- DECLARAÇÕES ANTECIPADAS ---
static void manipularBotaoChuva(unsigned long currentMillis, bool& debouncedRainButtonJustPressed);
static String obterCategoriaNivelAgua(float distance);
static String obterCategoriaIntensidadeChuva(int rainfall); // Assinatura mantida
static void publicarDadosSensores(const String& waterCategory, const String& rainCategory, unsigned long currentMillis);
static void atualizarFeedbackLEDs(const String& waterCategory, const String& rainCategory, 
                                  bool debouncedRainButtonJustPressed, unsigned long currentMillis);
static void gerenciarStatusRiscoEAlertas(float distance, unsigned long currentMillis);
float readDistanceHCSR04();
void mqtt_callback(char* topic, byte* payload, unsigned int length);
void mqtt_reconnect();
void setup_wifi();

// --- IMPLEMENTAÇÕES ---
float readDistanceHCSR04() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration_us = pulseIn(ECHO_PIN, HIGH, HCSR04_PULSE_TIMEOUT_US);
  return (duration_us > 0) ? (duration_us * 0.0343f / 2.0f) : 400.0f;
}

void mqtt_callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Mensagem recebida no topico: "); Serial.println(topic);
  char payloadBuffer[256];
  unsigned int copyLength = min((unsigned int)sizeof(payloadBuffer) - 1, length);
  strncpy(payloadBuffer, (char*)payload, copyLength);
  payloadBuffer[copyLength] = '\0';
  String payloadStr = String(payloadBuffer);
  payloadStr.toLowerCase();

  Serial.print("DEBUG (ESP32 Callback): Payload String para indexOf: '"); 
  Serial.print(payloadStr);                             
  Serial.println("'");   

  if (String(topic) == String(MQTT_TOPIC_COMMAND)) {
    if (payloadStr.indexOf("\"system_risk\":\"high\"") != -1) {
      mqtt_high_risk_active = true;
      Serial.println("MQTT CMD: Comando de ALTO RISCO recebido e ativado!");
    } else if (payloadStr.indexOf("\"system_risk\":\"normal\"") != -1 || 
               payloadStr.indexOf("\"system_risk\":\"clear\"") != -1) {
      mqtt_high_risk_active = false;
      Serial.println("MQTT CMD: Comando de risco normal/limpo recebido. ALTO RISCO via MQTT desativado.");
    } else {
      Serial.println("MQTT CMD: Comando desconhecido ou payload nao reconhecido.");
    }
  }
  Serial.println("-----------------------");
}

void mqtt_reconnect() { /* ... (código igual à versão V4 do seu sketch) ... */ 
  while (!mqttClient.connected()) {
    Serial.print("Tentando conectar ao Broker MQTT: "); Serial.print(MQTT_BROKER);                        
    Serial.print(" (Cliente ID: "); Serial.print(MQTT_CLIENT_ID); Serial.println(")");
    if (millis() - mqttLedBlinkPreviousMillis > MQTT_LED_RECONNECT_BLINK_INTERVAL_MS) {
      mqttLedBlinkPreviousMillis = millis(); 
      digitalWrite(LED_MQTT_PIN, !digitalRead(LED_MQTT_PIN)); 
    }
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("Conectado ao Broker MQTT!"); 
      digitalWrite(LED_MQTT_PIN, HIGH); 
      if (mqttClient.subscribe(MQTT_TOPIC_COMMAND)){
        Serial.print("Subscrito ao topico de comando: "); Serial.println(MQTT_TOPIC_COMMAND);
      } else {
        Serial.println("Falha ao subscrever ao topico de comando.");
      }
    } else {
      Serial.print("Falha na conexao MQTT, rc="); Serial.print(mqttClient.state());
      Serial.print(" Tentando novamente em "); Serial.print(MQTT_RECONNECT_RETRY_MS / 1000); Serial.println(" segundos...");
      unsigned long startWait = millis(); 
      while(millis() - startWait < MQTT_RECONNECT_RETRY_MS) {
        if (millis() - mqttLedBlinkPreviousMillis > MQTT_LED_RECONNECT_BLINK_INTERVAL_MS / 2) {
            mqttLedBlinkPreviousMillis = millis(); 
            digitalWrite(LED_MQTT_PIN, !digitalRead(LED_MQTT_PIN));
        }
        delay(100); 
      }
    }
  }
}

void setup_wifi() { /* ... (código igual à versão V4 do seu sketch) ... */ 
  delay(10); 
  Serial.println(); Serial.print("Conectando a rede Wi-Fi: "); Serial.println(SSID);
  WiFi.begin(SSID, PASSWORD); 
  unsigned long wifiConnectStartTime = millis(); 
  unsigned long wifiLedBlinkPreviousMillis = 0; 
  bool wifiLedState = LOW; 
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - wifiConnectStartTime > WIFI_CONNECT_TIMEOUT_MS) {
        Serial.println("\nFalha ao conectar ao Wi-Fi (timeout)!"); 
        digitalWrite(LED_MQTT_PIN, LOW); 
        return; 
    }
    if(millis() - wifiLedBlinkPreviousMillis > WIFI_LED_CONNECT_BLINK_INTERVAL_MS) {
        wifiLedBlinkPreviousMillis = millis(); 
        wifiLedState = !wifiLedState;            
        digitalWrite(LED_MQTT_PIN, wifiLedState); 
    }
    Serial.print("."); delay(50); 
  }
  digitalWrite(LED_MQTT_PIN, LOW); 
  Serial.println("\nWi-Fi conectado!"); Serial.print("Endereco IP: "); Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  Serial.println("FloodSentry AI - ESP32 com Estado de Alerta Crítico e Categorias Chuva V2");
  pinMode(TRIG_PIN, OUTPUT); pinMode(ECHO_PIN, INPUT);
  pinMode(RAIN_BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_MQTT_PIN, OUTPUT); pinMode(LED_RAIN_PIN, OUTPUT);
  pinMode(LED_WATER_PIN, OUTPUT); pinMode(LED_RISK_PIN, OUTPUT);
  digitalWrite(LED_MQTT_PIN, LOW); digitalWrite(LED_RAIN_PIN, LOW); 
  digitalWrite(LED_WATER_PIN, LOW); digitalWrite(LED_RISK_PIN, LOW); 
  setup_wifi();
  if (WiFi.status() == WL_CONNECTED) {
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(mqtt_callback);
  }
  Serial.println("Setup principal concluido.");
}

void loop() {
  unsigned long currentMillisLoop = millis();
  if (WiFi.status() == WL_CONNECTED) { 
    if (!mqttClient.connected()) { mqtt_reconnect(); }
    mqttClient.loop();
  } else {
    Serial.println("WiFi desconectado. Tentando reconectar MQTT...");
    mqtt_reconnect(); 
  }
  float distanceCm = readDistanceHCSR04();
  bool debouncedRainButtonJustPressed = false;
  manipularBotaoChuva(currentMillisLoop, debouncedRainButtonJustPressed);
  String waterLevelCategory = obterCategoriaNivelAgua(distanceCm);
  String rainIntensityCategory = obterCategoriaIntensidadeChuva(accumulatedRainfall); // Chamada da função corrigida
  publicarDadosSensores(waterLevelCategory, rainIntensityCategory, currentMillisLoop);
  atualizarFeedbackLEDs(waterLevelCategory, rainIntensityCategory, debouncedRainButtonJustPressed, currentMillisLoop);
  gerenciarStatusRiscoEAlertas(distanceCm, currentMillisLoop); 
  delay(MAIN_LOOP_DELAY_MS);
}

static void manipularBotaoChuva(unsigned long currentMillis, bool& debouncedRainButtonJustPressed) {
  debouncedRainButtonJustPressed = false; 
  bool currentRainButtonReading = (digitalRead(RAIN_BUTTON_PIN) == LOW);
  if (currentRainButtonReading != lastDebouncedRainButtonState) {
    lastRainButtonPressTime = currentMillis;
  }
  if ((currentMillis - lastRainButtonPressTime) > DEBOUNCE_DELAY_MS) {
    if (currentRainButtonReading != rainButtonPressedState) { 
      rainButtonPressedState = currentRainButtonReading; 
      if (rainButtonPressedState) { 
        accumulatedRainfall++; 
        debouncedRainButtonJustPressed = true; 
        Serial.print("Botao de Chuva Pressionado! Chuva Acumulada: "); Serial.println(accumulatedRainfall);
      }
    }
  }
  lastDebouncedRainButtonState = currentRainButtonReading; 
}

static String obterCategoriaNivelAgua(float distance) {
  if (distance < WATER_LEVEL_HIGH_THRESHOLD_CM) return "Alto";  
  if (distance < WATER_LEVEL_MEDIUM_THRESHOLD_CM) return "Medio";
  return "Baixo"; 
}

// ----- FUNÇÃO DE CATEGORIA DE CHUVA CORRIGIDA -----
static String obterCategoriaIntensidadeChuva(int rainfall) {
  if (rainfall == 0) { // Exatamente 0 cliques
    return "Nenhuma";
  } else if (rainfall < RAINFALL_MODERATE_THRESHOLD) { // Se RAINFALL_MODERATE_THRESHOLD = 5, aqui é 1 a 4
    return "Leve";
  } else if (rainfall < RAINFALL_HEAVY_THRESHOLD) { // Se RAINFALL_HEAVY_THRESHOLD = 10, aqui é 5 a 9
    return "Moderada";
  } else { // >= RAINFALL_HEAVY_THRESHOLD
    return "Pesada";
  }
}

static void publicarDadosSensores(const String& waterCategory, const String& rainCategory, unsigned long currentMillis) {
  if (mqttClient.connected() && (currentMillis - lastMqttPublishTime >= MQTT_PUBLISH_INTERVAL_MS)) {
    lastMqttPublishTime = currentMillis; 
    char waterPayload[60];
    sprintf(waterPayload, "{\"level_category\": \"%s\"}", waterCategory.c_str());
    if (mqttClient.publish(MQTT_TOPIC_WATER_LEVEL, waterPayload)) {
      Serial.print("Publicado em WATER_LEVEL: "); Serial.println(waterPayload);
    } else { Serial.println("Falha ao publicar em WATER_LEVEL."); }
    char rainPayload[60];
    sprintf(rainPayload, "{\"intensity_category\": \"%s\"}", rainCategory.c_str());
    if (mqttClient.publish(MQTT_TOPIC_RAINFALL, rainPayload)) {
      Serial.print("Publicado em RAINFALL: "); Serial.println(rainPayload);
    } else { Serial.println("Falha ao publicar em RAINFALL.");}
  }
}

static void atualizarFeedbackLEDs(const String& waterCategory, const String& rainCategory, 
                                  bool debouncedRainButtonJustPressed, unsigned long currentMillis) {
  if (waterCategory == "Alto") { digitalWrite(LED_WATER_PIN, HIGH); } 
  else if (waterCategory == "Medio") {
    if (currentMillis - waterLedBlinkPreviousMillis >= WATER_LED_BLINK_INTERVAL_MS) {
      waterLedBlinkPreviousMillis = currentMillis; waterLedState = !waterLedState; 
      digitalWrite(LED_WATER_PIN, waterLedState); }
  } else { digitalWrite(LED_WATER_PIN, LOW); }
  bool isHeavyRain = (rainCategory == "Pesada"); 
  bool isModerateRain = (rainCategory == "Moderada");
  bool isLightRain = (rainCategory == "Leve"); // Nova verificação

  if (debouncedRainButtonJustPressed) {
    digitalWrite(LED_RAIN_PIN, HIGH); 
    rainLedFlashEndTime = currentMillis + RAIN_LED_FLASH_DURATION_MS;
  }
  if (isHeavyRain) {
    if (currentMillis - rainLedHeavyBlinkPreviousMillis >= RAIN_LED_HEAVY_BLINK_INTERVAL_MS) {
      rainLedHeavyBlinkPreviousMillis = currentMillis; rainLedHeavyState = !rainLedHeavyState; 
      digitalWrite(LED_RAIN_PIN, rainLedHeavyState); }
  } else if (isModerateRain) {
      digitalWrite(LED_RAIN_PIN, HIGH); 
  } else if (isLightRain) { // LED aceso para chuva leve também
      digitalWrite(LED_RAIN_PIN, HIGH);
  } else { // Nenhuma
    if (currentMillis >= rainLedFlashEndTime && !isModerateRain && !isHeavyRain && !isLightRain) { // Garante que não desliga se ainda for moderada/pesada/leve
       digitalWrite(LED_RAIN_PIN, LOW);
    }
  }
}

static void gerenciarStatusRiscoEAlertas(float distance, unsigned long currentMillis) {
  bool local_high_risk_condition_now = (distance < CRITICAL_DISTANCE_THRESHOLD_CM && distance > 0.0f); 
  if (local_high_risk_condition_now || mqtt_high_risk_active) {
    digitalWrite(LED_RISK_PIN, HIGH); 
    if (local_high_risk_condition_now && !mqtt_high_risk_active) {
      Serial.println("ALERTA LOCAL (SENSOR): Risco de Enchente Iminente!");
    }
  } else {
    digitalWrite(LED_RISK_PIN, LOW); 
  }

  // Gerenciamento e Publicação do ESTADO do Alerta Crítico Local
  if (local_high_risk_condition_now != esp32_critical_alert_is_currently_active) {
    if (local_high_risk_condition_now) {
      esp32_critical_alert_is_currently_active = true;
      if (mqttClient.connected()) {
        char alertPayload[120]; 
        snprintf(alertPayload, sizeof(alertPayload), 
                 "{\"type\": \"imminent_flood_risk\", \"status\": \"ACTIVE\", \"cause\": \"local_sensor_reading\", \"distance_cm\": %.2f}", 
                 distance);
        if(mqttClient.publish(MQTT_TOPIC_CRITICAL_ALERT_STATUS, alertPayload)) { 
            Serial.print("MQTT Publicado [CRITICAL STATUS]: "); Serial.println(alertPayload);
        } else { Serial.println("Falha ao publicar ALERTA CRITICO ATIVO via MQTT.");}
      }
    } else { // Condição de risco local acabou de ser NORMALIZADA
      esp32_critical_alert_is_currently_active = false;
      if (mqttClient.connected()) {
        char clearPayload[100];
        snprintf(clearPayload, sizeof(clearPayload), 
                 "{\"type\": \"imminent_flood_risk\", \"status\": \"CLEARED\", \"cause\": \"local_sensor_reading\"}");
        if(mqttClient.publish(MQTT_TOPIC_CRITICAL_ALERT_STATUS, clearPayload)) {
            Serial.print("MQTT Publicado [CRITICAL STATUS]: "); Serial.println(clearPayload);
        } else { Serial.println("Falha ao publicar ALERTA CRITICO NORMALIZADO via MQTT.");}
      }
    }
  }
}
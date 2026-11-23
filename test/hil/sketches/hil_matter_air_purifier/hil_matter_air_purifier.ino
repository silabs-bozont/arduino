/*
   HIL Matter air purifier

   Combines fan control echoes with a cycling air-quality value (no button /
   no SGP40). Used by test/hil matter_air_purifier.
 */
#include <Matter.h>
#include <MatterAirPurifier.h>

using AirQuality = MatterAirQuality::AirQuality_t;

MatterAirPurifier matter_air_purifier;

static const AirQuality k_air_quality_cycle[] = {
  AirQuality::GOOD,
  AirQuality::FAIR,
  AirQuality::MODERATE,
  AirQuality::POOR,
  AirQuality::VERY_POOR,
  AirQuality::EXTREMELY_POOR,
};
static const size_t k_air_quality_cycle_count =
  sizeof(k_air_quality_cycle) / sizeof(k_air_quality_cycle[0]);

static const char* air_quality_to_string(AirQuality value)
{
  switch (value) {
    case AirQuality::GOOD:
      return "good";
    case AirQuality::FAIR:
      return "fair";
    case AirQuality::MODERATE:
      return "moderate";
    case AirQuality::POOR:
      return "poor";
    case AirQuality::VERY_POOR:
      return "very poor";
    case AirQuality::EXTREMELY_POOR:
      return "extremely poor";
    case AirQuality::UNKNOWN:
      return "unknown";
    default:
      return "undefined value";
  }
}

void setup()
{
  Serial.begin(115200);
  Matter.set_product_name("Matter air purifier");
  Matter.begin();
  matter_air_purifier.begin();

  Serial.println("Matter air purifier HIL");

  if (!Matter.isDeviceCommissioned()) {
    Serial.println("Matter device is not commissioned");
    Serial.println("Commission it to your Matter hub with the manual pairing code or QR code");
    Serial.printf("Manual pairing code: %s\n", Matter.getManualPairingCode().c_str());
    Serial.printf("QR code URL: %s\n", Matter.getOnboardingQRCodeUrl().c_str());
  }
  while (!Matter.isDeviceCommissioned()) {
    delay(200);
  }

  Serial.println("Waiting for Thread network...");
  while (!Matter.isDeviceThreadConnected()) {
    delay(200);
  }
  Serial.println("Connected to Thread network");

  Serial.println("Waiting for Matter device discovery...");
  while (!matter_air_purifier.is_online()) {
    delay(200);
  }
  Serial.println("Matter device is now online");

  // Percent first, then Off — SetFanPercentSetting turns Off→On when percent > 0.
  matter_air_purifier.set_fan_percent(80);
  matter_air_purifier.set_fan_onoff(false);
}

void loop()
{
  static size_t cycle_index = 0;
  static uint32_t last_aq_action = 0;
  static uint8_t fan_last_speed = 0u;
  static bool fan_last_mode = false;

  // Cycle air quality every 10s (no button)
  if ((last_aq_action + 10000) < millis()) {
    last_aq_action = millis();
    AirQuality value = k_air_quality_cycle[cycle_index];
    matter_air_purifier.set_air_quality(value);
    Serial.printf("Current air quality: %s\n", air_quality_to_string(value));
    cycle_index = (cycle_index + 1) % k_air_quality_cycle_count;
  }

  uint8_t fan_current_speed = matter_air_purifier.get_fan_percent();
  if (fan_current_speed != fan_last_speed) {
    fan_last_speed = fan_current_speed;
    Serial.print("Fan speed: ");
    Serial.print(fan_current_speed);
    Serial.println("%");
  }

  bool fan_current_mode = matter_air_purifier.get_fan_onoff();
  if (fan_current_mode != fan_last_mode) {
    fan_last_mode = fan_current_mode;
    if (fan_current_mode) {
      Serial.println("Fan ON");
    } else {
      Serial.println("Fan OFF");
    }
  }
}

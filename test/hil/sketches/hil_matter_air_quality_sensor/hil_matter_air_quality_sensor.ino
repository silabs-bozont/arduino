/*
   HIL Matter air quality sensor

   Cycles AirQuality enum values every 10 seconds without a physical SGP40.
   Used by test/hil matter_air_quality_sensor (the library example needs hardware).
 */
#include <Matter.h>
#include <MatterAirQuality.h>

using AirQuality = MatterAirQuality::AirQuality_t;

MatterAirQuality matter_air_quality_sensor;

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
  Matter.set_product_name("Matter air quality sensor");
  Matter.begin();
  matter_air_quality_sensor.begin();

  Serial.println("Matter air quality sensor HIL");

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
  while (!matter_air_quality_sensor.is_online()) {
    delay(200);
  }
  Serial.println("Matter device is now online");
}

void loop()
{
  static size_t cycle_index = 0;
  static uint32_t last_action = 0;

  if ((last_action + 10000) < millis()) {
    last_action = millis();
    AirQuality value = k_air_quality_cycle[cycle_index];
    matter_air_quality_sensor.set_air_quality(value);
    Serial.printf("Current air quality: %s\n", air_quality_to_string(value));
    cycle_index = (cycle_index + 1) % k_air_quality_cycle_count;
  }
}

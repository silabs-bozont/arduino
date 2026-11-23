/*
   HIL Matter rain sensor

   Toggles rain state every 10 seconds without a physical button.
   Used by test/hil matter_rain_sensor (the library example needs BTN_BUILTIN).
 */
#include <Matter.h>
#include <MatterRain.h>

MatterRain matter_rain_sensor;

void setup()
{
  Serial.begin(115200);
  Matter.set_product_name("Matter rain sensor");
  Matter.begin();
  matter_rain_sensor.begin();

  Serial.println("Matter rain sensor HIL");

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
  while (!matter_rain_sensor.is_online()) {
    delay(200);
  }
  Serial.println("Matter device is now online");
}

void loop()
{
  static uint32_t last_action = 0;
  // Wait 10 seconds
  if ((last_action + 10000) < millis()) {
    last_action = millis();
    // Toggle the state of the rain sensor (true = raining, false = dry)
    bool new_state = !matter_rain_sensor.get_measured_value();
    matter_rain_sensor = new_state;
    Serial.printf("Current rain sensor state: %s\n", new_state ? "raining" : "dry");
  }
}

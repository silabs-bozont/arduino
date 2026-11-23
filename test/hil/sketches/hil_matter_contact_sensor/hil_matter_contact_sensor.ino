/*
   HIL Matter contact sensor

   Toggles contact state every 10 seconds without a physical button.
   Used by test/hil matter_contact_sensor (the library example needs BTN_BUILTIN).
 */
#include <Matter.h>
#include <MatterContact.h>

MatterContact matter_contact_sensor;

void setup()
{
  Serial.begin(115200);
  Matter.set_product_name("Matter contact sensor");
  Matter.begin();
  matter_contact_sensor.begin();

  Serial.println("Matter contact sensor HIL");

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
  while (!matter_contact_sensor.is_online()) {
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
    // Toggle the state of the contact sensor
    bool new_state = !matter_contact_sensor.get_state();
    matter_contact_sensor = new_state;
    Serial.printf("Current contact state: %s\n", new_state ? "detected" : "lost");
  }
}

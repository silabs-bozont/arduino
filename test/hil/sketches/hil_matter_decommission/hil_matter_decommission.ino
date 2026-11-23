/*
   HIL Matter decommission

   On/off lightbulb that decommissions when the host sends "decommission" over Serial.
   Used by test/hil matter_decommission (the library example needs a 10s button hold).
 */
#include <Matter.h>
#include <MatterLightbulb.h>

MatterLightbulb matter_bulb;

static void handle_serial_commands();

void setup()
{
  Serial.begin(115200);
  Matter.set_product_name("Matter on/off lightbulb");
  Matter.begin();
  matter_bulb.begin();

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LED_BUILTIN_INACTIVE);

  Serial.println("Matter decommission HIL");

  if (!Matter.isDeviceCommissioned()) {
    Serial.println("Matter device is not commissioned");
    Serial.println("Commission it to your Matter hub with the manual pairing code or QR code");
    Serial.printf("Manual pairing code: %s\n", Matter.getManualPairingCode().c_str());
    Serial.printf("QR code URL: %s\n", Matter.getOnboardingQRCodeUrl().c_str());
  }
  while (!Matter.isDeviceCommissioned()) {
    // Retransmit so HIL can match after a reboot even if early boot lines were missed
    static uint32_t last_hint = 0;
    if ((last_hint + 5000) < millis()) {
      last_hint = millis();
      Serial.println("Matter device is not commissioned");
    }
    delay(200);
  }

  Serial.println("Waiting for Thread network...");
  while (!Matter.isDeviceThreadConnected()) {
    handle_serial_commands();
    delay(200);
  }
  Serial.println("Connected to Thread network");

  Serial.println("Waiting for Matter device discovery...");
  while (!matter_bulb.is_online()) {
    handle_serial_commands();
    delay(200);
  }
  Serial.println("Matter device is now online");
  Serial.println("HIL decommission ready");
}

void loop()
{
  static bool matter_lightbulb_last_state = false;
  bool matter_lightbulb_current_state = matter_bulb.get_onoff();

  if (matter_lightbulb_current_state && !matter_lightbulb_last_state) {
    matter_lightbulb_last_state = matter_lightbulb_current_state;
    digitalWrite(LED_BUILTIN, LED_BUILTIN_ACTIVE);
    Serial.println("Bulb ON");
  }

  if (!matter_lightbulb_current_state && matter_lightbulb_last_state) {
    matter_lightbulb_last_state = matter_lightbulb_current_state;
    digitalWrite(LED_BUILTIN, LED_BUILTIN_INACTIVE);
    Serial.println("Bulb OFF");
  }

  handle_serial_commands();
}

static void handle_serial_commands()
{
  static String line;

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (line.length() == 0) {
        continue;
      }
      if (line.equals("decommission")) {
        if (!Matter.isDeviceCommissioned()) {
          Serial.println("Device is already not commissioned");
          line = "";
          continue;
        }
        Serial.println("Starting decommissioning process, device will reboot...");
        digitalWrite(LED_BUILTIN, LED_BUILTIN_INACTIVE);
        // Does not return; device reboots after factory reset
        Matter.decommission();
      } else {
        Serial.printf("Unknown command: %s\n", line.c_str());
      }
      line = "";
    } else {
      line += c;
    }
  }
}

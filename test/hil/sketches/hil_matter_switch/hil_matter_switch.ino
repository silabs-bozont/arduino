/*
   HIL Matter switch

   Momentary switch driven by Serial "press" / "release" instead of BTN_BUILTIN.
   Used by test/hil matter_switch (the library example needs a physical button).
 */
#include <Matter.h>
#include <MatterSwitch.h>

MatterSwitch matter_switch;

static void handle_serial_commands();

void setup()
{
  Serial.begin(115200);
  Matter.set_product_name("Matter switch");
  Matter.begin();
  matter_switch.begin();

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LED_BUILTIN_INACTIVE);

  Serial.println("Matter switch HIL");

  if (!Matter.isDeviceCommissioned()) {
    Serial.println("Matter device is not commissioned");
    Serial.println("Commission it to your Matter hub with the manual pairing code or QR code");
    Serial.printf("Manual pairing code: %s\n", Matter.getManualPairingCode().c_str());
    Serial.printf("QR code URL: %s\n", Matter.getOnboardingQRCodeUrl().c_str());
  }
  while (!Matter.isDeviceCommissioned()) {
    handle_serial_commands();
    delay(200);
  }

  Serial.println("Waiting for Thread network...");
  while (!Matter.isDeviceThreadConnected()) {
    handle_serial_commands();
    delay(200);
  }
  Serial.println("Connected to Thread network");

  Serial.println("Waiting for Matter device discovery...");
  while (!matter_switch.is_online()) {
    handle_serial_commands();
    delay(200);
  }
  Serial.println("Matter device is now online");
  Serial.println("HIL switch ready");
}

void loop()
{
  static bool switch_last_state = false;
  bool switch_current_state = matter_switch.get_state();

  if (switch_current_state && !switch_last_state) {
    switch_last_state = switch_current_state;
    digitalWrite(LED_BUILTIN, LED_BUILTIN_ACTIVE);
    Serial.println("Switch pressed");
  }

  if (!switch_current_state && switch_last_state) {
    switch_last_state = switch_current_state;
    digitalWrite(LED_BUILTIN, LED_BUILTIN_INACTIVE);
    Serial.println("Switch released");
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
      if (line.equals("press")) {
        matter_switch.set_state(true);
      } else if (line.equals("release")) {
        matter_switch.set_state(false);
      } else {
        Serial.printf("Unknown command: %s\n", line.c_str());
      }
      line = "";
    } else {
      line += c;
    }
  }
}

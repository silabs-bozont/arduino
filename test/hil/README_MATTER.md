# Matter HIL (Raspberry Pi Matter Hub)

Commissioning and on/off control run on a Silicon Labs **Matter Hub** image on a
Raspberry Pi. The host only builds/flashes the DUT and checks Serial. Matter HIL
tests are **opt-in** via `--matter-otbr <pi-ip>`.

## Pi image

Use the official Silicon Labs Matter Hub image (OTBR + chip-tool / `mattertool`):

- Download: https://www.silabs.com/documents/public/software/SilabsMatterPi_2.9.0-1.6-extension.zip
- Docs: https://docs.silabs.com/matter/latest/matter-prerequisites/matter-artifacts
- Setup: https://docs.silabs.com/matter/latest/matter-thread/raspi-img

Flash the extracted `.img` with Raspberry Pi Imager (**Use custom**). Default SSH
user/password on first boot: `ubuntu` / `ubuntu` (you may be forced to change it).

Connect an OpenThread **RCP** (EFR) to the Pi over USB (`/dev/ttyACM0`). RCP binaries:
https://github.com/SiliconLabs/matter_extension/releases (Assets → `ot-rcp-binaries-…`).

Prefer Ethernet for the Pi on the same LAN as the HIL host. Onboard Bluetooth
must be working (`hci0` present) for BLE commissioning; a reboot often clears
a failed `hciuart` bring-up on first boot.

Commissioning retries once on failure: fresh OTBR Thread network, longer
chip-tool `--timeout` (300s) so mid-CASE IPv6 flakes can recover, and a DUT
NVM clear + reflash via `before_retry` so BLE advertising is restored.

Operational chip-tool reads/writes also retry once after 5s on failure (same
OTBR `Network is unreachable` flake).

## Host SSH

When you pass `--matter-otbr <pi-ip>`, the runner prompts once for the Pi SSH
password (`getpass`) and keeps it in memory for that process only.

Optional env overrides (still not written to disk by the HIL scripts):

- `MATTER_OTBR_SSH_USER` (default `ubuntu`)
- `MATTER_OTBR_SSH_PASSWORD` (skips the interactive prompt)

## Run

```bash
cd test/hil
# Full HIL suite (Matter lightbulb included when --matter-otbr is set)
python3 test_hil.py <board> <port> --matter-otbr <pi-ip>

# Matter Pi tests only (matter variant + matter_lightbulb)
python3 test_hil.py <board> <port> --matter-otbr <pi-ip> --matter-only
```

Without `--matter-otbr`, Matter Pi HIL cases are skipped. Current coverage:

- on/off lightbulb (`matter_lightbulb`)
- dimmable lightbulb on/off + random brightness % (`matter_lightbulb_dimmable`)
- on/off outlet (`matter_on_off_outlet`)
- fan modes + random speed % (`matter_fan`)
- temperature sensor CPU reading (`matter_temp_sensor`)
- humidity sensor +0.5% increment (`matter_humidity_sensor`)
- illuminance sensor +15 lx increment (`matter_illuminance_sensor`)
- CO2 sensor +15 ppm increment (`matter_co2_sensor`)
- window covering open/close, go-to %, stop (`matter_window_covering`)

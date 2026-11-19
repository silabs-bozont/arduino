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

Before each commission the Pi resets hub state: `killall chip-tool`, clear
`/tmp/chip_*`, restart `otbr-agent`, bounce `hci0`, then a new Thread network
and wait until `ot-ctl state` is leader/router (avoids mid-CASE
`Network is unreachable` from stale IPv6 border routes). Commissioning still
retries once on failure with a DUT NVM clear + reflash via `before_retry`.

Operational chip-tool reads/writes retry once on failure. After CASE/IPv6
flakes (`Network is unreachable` / DUT `busy`), the retry waits ~70s (or the
DUT-reported busy window) and `killall chip-tool` clears a leftover process
from an SSH timeout. That wait is expected and can look idle in the log.

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
- thermostat Off/Heat + random setpoints + limit clamp (`matter_thermostat`)
- temperature sensor CPU reading (`matter_temp_sensor`)
- humidity sensor +0.5% increment (`matter_humidity_sensor`)
- pressure sensor +5 hPa increment (`matter_pressure_sensor`)
- flow sensor +0.5 m3/h increment (`matter_flow_sensor`)
- illuminance sensor +15 lx increment (`matter_illuminance_sensor`)
- CO2 sensor +15 ppm increment (`matter_co2_sensor`)
- CO sensor +15 ppb increment (`matter_co_sensor`)
- TVOC sensor +15 ppb increment (`matter_tvoc_sensor`)
- window covering open/close, go-to %, stop (`matter_window_covering`)

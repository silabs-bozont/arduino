# arduino_ble_hci

Local SLC extension for **BLE (Arduino)** builds. Passed to SLC via `--sdk-package-path`.

## Why

1. **`bluetooth_hci_reset`** – ArduinoBLE needs `sl_btctrl_hci_reset()`. SiSDK 2026.x put that code under `bluetooth_hci`, which also selects RCP and requires a UART/CPC transport. This extension exposes only the reset sources (vendored from `bluetooth_le_controller/utils/hci_packet`).

2. **`sl_bt_controller_compat`** – ArduinoBLE 2.x calls `sl_bt_controller_init` / `sl_bt_controller_deinit` (GSDK 4.x names). SiSDK 2026.x renamed them to `sl_btctrl_init` / `sl_btctrl_deinit`. Thin wrappers live here.

## Refreshing vendored reset sources

When bumping SiSDK, re-copy:

```text
bluetooth_le_controller/utils/hci_packet/src/sl_btctrl_reset.c  -> src/
bluetooth_le_controller/utils/hci_packet/inc/sl_btctrl_reset.h  -> inc/
```

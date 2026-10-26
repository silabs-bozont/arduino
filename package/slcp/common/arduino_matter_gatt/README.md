# arduino_matter_gatt

Local SLC extension for **Matter** builds. Passed to SLC via `--sdk-package-path`.

## Why

Upstream `matter_gatt_static` ships a CHIPoBLE `gatt_configuration.btconf` **without**
capability tags. Arduino Matter+BLE examples call
`sl_bt_gatt_server_set_capabilities(static_service_gatt_none)` so they can hide
static CHIPoBLE/GAP/DIS and own Generic Access via dynamic GATT.

SLCP `config_file` override cannot replace that btconf: `matter_gatt_static` has no
`file_id`, and SLC reports `config_file -> file_id: missing` then keeps the upstream
file. This extension provides the same `matter_gatt_static` capability with an
Arduino btconf that declares the capabilities (and a `file_id` for future overrides).

## Refreshing the btconf

Start from Matter extension
`third_party/matter_sdk/examples/platform/silabs/gatt_configuration.btconf`, then
restore the Arduino `<capabilities_declare>` / per-service `<capabilities>` blocks.

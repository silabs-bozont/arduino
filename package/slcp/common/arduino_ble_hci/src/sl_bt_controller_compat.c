/***************************************************************************//**
 * Compatibility wrappers for ArduinoBLE (HCISilabsTransport).
 *
 * ArduinoBLE 2.x calls sl_bt_controller_init/deinit (GSDK 4.x names).
 * SiSDK 2026.x renamed these to sl_btctrl_init/deinit.
 * Provided via the arduino_ble_hci extension — extending the SDK.
 *
 * We intentionally do not select the bluetooth_hci RCP component (it pulls a
 * UART/CPC HCI transport that conflicts with Arduino Serial/VCOM). Without
 * SL_CATALOG_BLUETOOTH_RCP_PRESENT, sl_btctrl_init() skips
 * sl_btctrl_configure_le_buffer_size(), and ACL/ATT traffic fails after
 * connect. Configure the host->controller ACL packet budget here instead.
 ******************************************************************************/

#include "sl_btctrl_linklayer.h"
#include "sl_btctrl_config.h"

void sl_bt_controller_init(void)
{
  sl_btctrl_configure_le_buffer_size(SL_BT_CONTROLLER_LE_BUFFER_SIZE_MAX);
  (void)sl_btctrl_init();
}

void sl_bt_controller_deinit(void)
{
  sl_btctrl_deinit();
}

#ifndef SL_BT_CONTROLLER_COMPAT_H
#define SL_BT_CONTROLLER_COMPAT_H

#ifdef __cplusplus
extern "C" {
#endif

/* ArduinoBLE expects these GSDK 4.x names; SiSDK 2026.x uses sl_btctrl_*. */
void sl_bt_controller_init(void);
void sl_bt_controller_deinit(void);

#ifdef __cplusplus
}
#endif

#endif /* SL_BT_CONTROLLER_COMPAT_H */

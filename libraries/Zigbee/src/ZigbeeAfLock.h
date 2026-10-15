/*
 * This file is part of the Silicon Labs Arduino Core
 *
 * The MIT License (MIT)
 *
 * Copyright 2026 Silicon Laboratories Inc. www.silabs.com
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef ARDUINO_ZIGBEE_AF_LOCK_H
#define ARDUINO_ZIGBEE_AF_LOCK_H

extern "C" {
#include "af.h"
#include "FreeRTOS.h"
#include "task.h"
}

// Guard for application framework APIs called from outside AF callback context
// like the Arduino task. Pattern: acquire -> AF work -> release -> wakeup.
// The AF mutex is recursive - nested guards are safe to use.
class ZigbeeAfLock {
public:
  ZigbeeAfLock()
  {
    // SiSDK 2026 creates the AF mutex in the Zigbee AF RTOS task after the
    // kernel starts. Arduino setup() (prio 1) can call Zigbee APIs before that
    // task has finished init — acquire then asserts in util.c. SDK z3light
    // avoids this via sl_main (app_init runs only after stack init). Until the
    // Arduino core moves to sl_main, yield once so the AF task (prio 48) can
    // complete init. Do not poll sli_zigbee_af_mutex_id — that deadlocks.
    // ToDo: remove this workaround once the Arduino core moves to sl_main
    static bool af_settle_done = false;
    if (!af_settle_done) {
      vTaskDelay(pdMS_TO_TICKS(2000));
      af_settle_done = true;
    }
    sl_zigbee_af_acquire_lock();
  }

  ~ZigbeeAfLock()
  {
    sl_zigbee_af_release_lock();
    sl_zigbee_wakeup_common_task();
  }

  ZigbeeAfLock(const ZigbeeAfLock&) = delete;
  ZigbeeAfLock& operator=(const ZigbeeAfLock&) = delete;
};

#endif // ARDUINO_ZIGBEE_AF_LOCK_H

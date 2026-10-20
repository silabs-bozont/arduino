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

#ifndef PLATFORM_SILABS_TRACING_SILABSTRACINGCONFIG_H_
#define PLATFORM_SILABS_TRACING_SILABSTRACINGCONFIG_H_

// <<< Use Configuration Wizard in Context Menu >>>

// <q TRACING_RUNTIME_STATS> Enable FreeRTOS runtime statistics collection
// <i> Default: 0
#define TRACING_RUNTIME_STATS 0

// <o TRACING_RUNTIME_STATS_MAX_TASKS> Maximum number of tasks to track for runtime statistics.
// <i> Default: 16
#define TRACING_RUNTIME_STATS_MAX_TASKS 16

// <q SL_TRACING_ENERGY_STATS> Enable energy mode statistics collection
// <i> Default: 0
#define SL_TRACING_ENERGY_STATS 0

// <o SL_TRACING_ENERGY_TRACES_SECONDS> Time to wait before outputting the results
// <i> Default: 600
#define SL_TRACING_ENERGY_TRACES_SECONDS 600

// <o SL_TRACING_ENERGY_TRACES_MAX> Maximum number of energy traces to store
// <i> Default: 3000
#define SL_TRACING_ENERGY_TRACES_MAX 3000

// <<< end of configuration section >>>

#endif // PLATFORM_SILABS_TRACING_SILABSTRACINGCONFIG_H_


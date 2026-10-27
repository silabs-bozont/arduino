/*
 * This file is part of the Silicon Labs Arduino Core
 *
 * The MIT License (MIT)
 *
 * Copyright 2025 Silicon Laboratories Inc. www.silabs.com
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

#ifndef SL_SILABS_TFLITE_MICRO_H
#define SL_SILABS_TFLITE_MICRO_H

#ifndef ARDUINO_SILABS_AIML_CAPABLE
  #error "Your board or currently selected protocol stack is not AI/ML capable. Please select an AI/ML capable board and protocol stack."
#endif

#include "sl_tflite_micro_model.h"
#include "sl_ml_tflite_micro_model.h"

#ifndef SL_TFLITE_MICRO_ARENA_SIZE
#define SL_TFLITE_MICRO_ARENA_SIZE 8192
#endif

// Arduino wrapper for the AI/ML SDK 3.x sl_ml_model_* API
class SilabsTFLiteMicroClass {
public:
  SilabsTFLiteMicroClass();

  /**
   * Build an sl_ml_model_handle_t for the sketch flatbuffer and load it.
   * @param arena_size Tensor arena bytes (default SL_TFLITE_MICRO_ARENA_SIZE).
   */
  sl_status_t begin(size_t arena_size = SL_TFLITE_MICRO_ARENA_SIZE);

  /** Run one inference (sl_ml_model_run). */
  sl_status_t run();

  /** Unload the model (sl_ml_model_deinit). */
  sl_status_t end();

  sl_ml_model_handle_t* handle();
  TfLiteTensor* input(size_t index = 0);
  TfLiteTensor* output(size_t index = 0);
  tflite::MicroInterpreter* interpreter();

private:
  sl_ml_model_handle_t* model_handle;
  uint8_t* arena;
  uint8_t* arena_buffers[1];
  int32_t arena_buffer_sizes[1];
  bool initialized;
};

extern SilabsTFLiteMicroClass SilabsTFLiteMicro;

#endif // SL_SILABS_TFLITE_MICRO_H

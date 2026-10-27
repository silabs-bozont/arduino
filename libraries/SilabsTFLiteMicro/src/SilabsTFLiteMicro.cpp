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

#include "SilabsTFLiteMicro.h"
#include "sl_tflite_micro_opcode_resolver.h"
#include <new>
#include <cstdlib>
#include <cstdint>

SilabsTFLiteMicroClass SilabsTFLiteMicro;

SilabsTFLiteMicroClass::SilabsTFLiteMicroClass() :
  model_handle(nullptr),
  arena(nullptr),
  initialized(false)
{
  arena_buffers[0] = nullptr;
  arena_buffer_sizes[0] = 0;
}

sl_status_t SilabsTFLiteMicroClass::begin(size_t arena_size)
{
  if (this->initialized) {
    return SL_STATUS_OK;
  }
  if (sl_tflite_model_array == nullptr || sl_tflite_model_len == 0 || arena_size == 0) {
    return SL_STATUS_INVALID_PARAMETER;
  }

  // malloc is 8-byte aligned; add padding so we can 16-byte-align for TFLM
  this->arena = static_cast<uint8_t*>(malloc(arena_size + 16));
  if (this->arena == nullptr) {
    return SL_STATUS_ALLOCATION_FAILED;
  }
  uintptr_t addr = reinterpret_cast<uintptr_t>(this->arena);
  uintptr_t aligned = (addr + 15u) & ~static_cast<uintptr_t>(15u);
  this->arena_buffers[0] = reinterpret_cast<uint8_t*>(aligned);
  this->arena_buffer_sizes[0] = static_cast<int32_t>(arena_size);

  SL_TFLITE_MICRO_OPCODE_RESOLVER(opcode_resolver);

  void* storage = malloc(sizeof(sl_ml_model_handle_t));
  if (storage == nullptr) {
    free(this->arena);
    this->arena = nullptr;
    this->arena_buffers[0] = nullptr;
    return SL_STATUS_ALLOCATION_FAILED;
  }

  this->model_handle = new (storage) sl_ml_model_handle_t(
    sl_tflite_model_array,
    static_cast<int>(sl_tflite_model_len),
    &opcode_resolver,
    this->arena_buffers,
    this->arena_buffer_sizes,
    1,
    16,
    nullptr);

  sl_status_t status = sl_ml_model_init(this->model_handle);
  if (status != SL_STATUS_OK) {
    this->model_handle->~sl_ml_model_handle_t();
    free(storage);
    this->model_handle = nullptr;
    free(this->arena);
    this->arena = nullptr;
    this->arena_buffers[0] = nullptr;
    return status;
  }

  this->initialized = true;
  return SL_STATUS_OK;
}

sl_status_t SilabsTFLiteMicroClass::run()
{
  if (!this->initialized || this->model_handle == nullptr) {
    return SL_STATUS_NOT_INITIALIZED;
  }
  return sl_ml_model_run(this->model_handle);
}

sl_status_t SilabsTFLiteMicroClass::end()
{
  if (!this->initialized || this->model_handle == nullptr) {
    return SL_STATUS_NOT_INITIALIZED;
  }

  sl_status_t status = sl_ml_model_deinit(this->model_handle);
  this->model_handle->~sl_ml_model_handle_t();
  free(this->model_handle);
  this->model_handle = nullptr;
  free(this->arena);
  this->arena = nullptr;
  this->arena_buffers[0] = nullptr;
  this->arena_buffer_sizes[0] = 0;
  this->initialized = false;
  return status;
}

sl_ml_model_handle_t* SilabsTFLiteMicroClass::handle()
{
  return this->model_handle;
}

TfLiteTensor* SilabsTFLiteMicroClass::input(size_t index)
{
  if (this->model_handle == nullptr) {
    return nullptr;
  }
  return this->model_handle->input_tensor(index);
}

TfLiteTensor* SilabsTFLiteMicroClass::output(size_t index)
{
  if (this->model_handle == nullptr) {
    return nullptr;
  }
  return this->model_handle->output_tensor(index);
}

tflite::MicroInterpreter* SilabsTFLiteMicroClass::interpreter()
{
  if (this->model_handle == nullptr || !this->model_handle->model.is_loaded()) {
    return nullptr;
  }
  return this->model_handle->model.interpreter();
}

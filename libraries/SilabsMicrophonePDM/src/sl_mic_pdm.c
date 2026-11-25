/***************************************************************************//**
 * @file
 * @brief PDM microphone driver
 *
 * Based on SiSDK boards/hardware/driver/mic/src/sl_mic_pdm.c with two Arduino
 * adaptations only:
 *   1. Runtime DIN/CLK pins + DSR (sketch provides pins; no sl_mic_pdm_config.h)
 *   2. get_n_samples / start_streaming start a fresh linked discard→fill DMA
 *      instead of patching the live discard ping-pong in the DONE IRQ.
 *      On Series 2 LDMA the next linked descriptor is loaded before the IRQ
 *      runs, so the stock SDK "flip reading_samples_to_buffer" handoff never
 *      installs the fill (empty buffer → inf dBSPL). A short discard after
 *      restart drops the CIC settle transient so levels match Studio/DMADRV.
 *******************************************************************************
 * # License
 * <b>Copyright 2020 Silicon Laboratories Inc. www.silabs.com</b>
 *******************************************************************************
 *
 * SPDX-License-Identifier: Zlib
 *
 * The licensor of this software is Silicon Laboratories Inc.
 *
 * This software is provided 'as-is', without any express or implied
 * warranty. In no event will the authors be held liable for any damages
 * arising from the use of this software.
 *
 * Permission is granted to anyone to use this software for any purpose,
 * including commercial applications, and to alter it and redistribute it
 * freely, subject to the following restrictions:
 *
 * 1. The origin of this software must not be misrepresented; you must not
 *    claim that you wrote the original software. If you use this software
 *    in a product, an acknowledgment in the product documentation would be
 *    appreciated but is not required.
 * 2. Altered source versions must be plainly marked as such, and must not be
 *    misrepresented as being the original software.
 * 3. This notice may not be removed or altered from any source distribution.
 *
 ******************************************************************************/
#include <stddef.h>
#include <stdint.h>
#include <math.h>
#include "sl_clock_manager.h"
#include "sl_device_clock.h"
#include "sl_dma_manager.h"
#include "sl_hal_ldma.h"
#include "sl_hal_pdm.h"
#include "sl_hal_gpio.h"
#include "sl_gpio.h"
#include "sl_mic.h"
#include "sl_sleeptimer.h"
#include "sl_device_peripheral.h"

#if (defined(SL_CATALOG_POWER_MANAGER_PRESENT))
#include "sl_power_manager.h"
#endif

#if !defined(_SILICON_LABS_32B_SERIES_2)
#error "SilabsMicrophonePDM requires Series 2 devices"
#endif

static bool dma_complete(uint32_t channel, uint32_t sequence_no, void *user_param);

static sl_gpio_t pdm_din_gpio;
static sl_gpio_t pdm_clk_gpio;

static sl_mic_buffer_ready_callback_t buffer_ready_callback = NULL;
static int16_t *sample_buffer;
static int16_t  *streaming_buffer[2];
static uint32_t sample_index;
static uint32_t sample_count;
static volatile bool reading_samples_to_buffer;
static volatile bool streaming_in_progress;
static bool mic_running;
static volatile bool mic_ready;
static bool initialized;
static uint8_t num_channels;
static uint32_t discard_buffer;

#define MIC_PDM_MAX_XFER  (SL_HAL_LDMA_DESCRIPTOR_MAX_XFER_SIZE)
/* Drop CIC/mic settle samples after each LDMA restart before the real fill. */
#define MIC_POST_RESTART_DISCARD  512U

static sl_dma_handle_t *dma_handle;
static uint8_t dma_channel_id;
static volatile uint32_t dma_sequence_no;

static const sl_hal_ldma_transfer_init_t dma_transfer_cfg =
  SL_HAL_LDMA_TRANSFER_CFG_PERIPHERAL(SL_HAL_LDMA_PERIPHERAL_SIGNAL_PDM_RXDATAV);

static sl_hal_ldma_descriptor_t dma_descriptor[2] = {
  SL_HAL_LDMA_DESCRIPTOR_LINKREL_P2M(SL_HAL_LDMA_CTRL_SIZE_WORD, &PDM->RXDATA, &discard_buffer, (MIC_PDM_MAX_XFER - 1), 1),
  SL_HAL_LDMA_DESCRIPTOR_LINKREL_P2M(SL_HAL_LDMA_CTRL_SIZE_WORD, &PDM->RXDATA, &discard_buffer, (MIC_PDM_MAX_XFER - 1), -1)
};

static sl_sleeptimer_timer_handle_t mic_wake_up_timer;

static void pdm_dma_irq_cb(void)
{
  (void)dma_complete((uint32_t)dma_channel_id, dma_sequence_no++, NULL);
}

static void timeout_callback(sl_sleeptimer_timer_handle_t *handle, void *data)
{
  (void)handle;
  (void)data;
  mic_ready = true;
}

static void pdm_ldma_start(void)
{
  dma_sequence_no = 0;
  sl_dma_manager_register_channel_irq_callback(dma_handle, dma_channel_id, pdm_dma_irq_cb);
  sl_hal_ldma_clear_interrupts(LDMA0, 1UL << dma_channel_id);
  sl_hal_ldma_init_transfer(LDMA0, dma_channel_id, &dma_transfer_cfg, &dma_descriptor[0]);
  sl_hal_ldma_enable_interrupts(LDMA0, 1UL << dma_channel_id);
  sl_hal_ldma_start_transfer(LDMA0, dma_channel_id);
}

static void pdm_ldma_start_discard_warmup(void)
{
  dma_descriptor[0].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_NONE;
  dma_descriptor[0].xfer.dst_addr   = (uint32_t)&discard_buffer;
  dma_descriptor[0].xfer.xfer_count = (MIC_PDM_MAX_XFER - 1);
  dma_descriptor[0].xfer.done_ifs   = 1;
  dma_descriptor[0].xfer.link       = 1;
  dma_descriptor[0].xfer.link_mode  = SL_HAL_LDMA_LINK_MODE_REL;
  dma_descriptor[0].xfer.link_addr  = 1 * SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

  dma_descriptor[1].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_NONE;
  dma_descriptor[1].xfer.dst_addr   = (uint32_t)&discard_buffer;
  dma_descriptor[1].xfer.xfer_count = (MIC_PDM_MAX_XFER - 1);
  dma_descriptor[1].xfer.done_ifs   = 1;
  dma_descriptor[1].xfer.link       = 1;
  dma_descriptor[1].xfer.link_mode  = SL_HAL_LDMA_LINK_MODE_REL;
  dma_descriptor[1].xfer.link_addr  = -1 * (int32_t)SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

  pdm_ldma_start();
}

static void pdm_ldma_start_discard_then_fill(void *dest, uint32_t fill_units)
{
  uint32_t discard_units = MIC_POST_RESTART_DISCARD;
  if (discard_units > MIC_PDM_MAX_XFER) {
    discard_units = MIC_PDM_MAX_XFER;
  }

  dma_descriptor[0].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_NONE;
  dma_descriptor[0].xfer.dst_addr   = (uint32_t)&discard_buffer;
  dma_descriptor[0].xfer.xfer_count = discard_units - 1;
  dma_descriptor[0].xfer.done_ifs   = 0;
  dma_descriptor[0].xfer.link       = 1;
  dma_descriptor[0].xfer.link_mode  = SL_HAL_LDMA_LINK_MODE_REL;
  dma_descriptor[0].xfer.link_addr  = 1 * SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

  dma_descriptor[1].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_ONE;
  dma_descriptor[1].xfer.dst_addr   = (uint32_t)dest;
  dma_descriptor[1].xfer.xfer_count = fill_units - 1;
  dma_descriptor[1].xfer.done_ifs   = 1;
  dma_descriptor[1].xfer.link       = 0;

  pdm_ldma_start();
}

/***************************************************************************//**
 *    Initializes the microphone
 ******************************************************************************/
sl_status_t sl_mic_init(GPIO_Port_TypeDef din_port,
                        unsigned int din_pin,
                        GPIO_Port_TypeDef clk_port,
                        unsigned int clk_pin,
                        uint32_t sample_rate,
                        uint8_t n_channels,
                        uint8_t dsr)
{
  sl_status_t status;

  if (n_channels < 1 || n_channels > 2) {
    return SL_STATUS_INVALID_PARAMETER;
  }

  pdm_din_gpio.port = (sl_gpio_port_t)din_port;
  pdm_din_gpio.pin = din_pin;
  pdm_clk_gpio.port = (sl_gpio_port_t)clk_port;
  pdm_clk_gpio.pin = clk_pin;

  sl_clock_manager_enable_bus_clock(SL_BUS_CLOCK_GPIO);
  sl_clock_manager_enable_bus_clock(SL_BUS_CLOCK_PDM);

  sl_gpio_set_pin_mode(&pdm_din_gpio, SL_GPIO_MODE_INPUT, 0);
  sl_gpio_set_pin_mode(&pdm_clk_gpio, SL_GPIO_MODE_PUSH_PULL, 0);

  sl_hal_gpio_set_slew_rate(&pdm_din_gpio, 0x7);
  sl_hal_gpio_set_slew_rate_alternate(pdm_din_gpio.port, 0x7);

  GPIO->PDMROUTE.ROUTEEN |= GPIO_PDM_ROUTEEN_CLKPEN;
  GPIO->PDMROUTE.DAT0ROUTE = (din_port << _GPIO_PDM_DAT0ROUTE_PORT_SHIFT)
                             | (din_pin << _GPIO_PDM_DAT0ROUTE_PIN_SHIFT);
  GPIO->PDMROUTE.CLKROUTE = (clk_port << _GPIO_PDM_CLKROUTE_PORT_SHIFT)
                            | (clk_pin << _GPIO_PDM_CLKROUTE_PIN_SHIFT);

  if (dsr < 3 || dsr > 73) {
    return SL_STATUS_INVALID_PARAMETER;
  }

  uint8_t gain = 31 - (1 + (uint32_t)(log10f(pow(dsr, 5)) / log10f(2)));

  uint32_t clock_freq;
  sl_clock_branch_t clock_branch;
  clock_branch = sl_device_peripheral_get_clock_branch(SL_PERIPHERAL_PDM);
  sl_clock_manager_get_clock_branch_frequency(clock_branch, &clock_freq);
  uint32_t prescaler_val = (clock_freq / (sample_rate * dsr)) - 1;

  if (prescaler_val > 1024) {
    return SL_STATUS_FAIL;
  }

  sl_hal_pdm_init_t init = SL_HAL_PDM_INIT_DEFAULT;
  init.clk_prescaler = prescaler_val;
  init.down_sampling_rate = dsr;
  init.gain = gain;

  if (n_channels == 1) {
    init.data_format = SL_HAL_PDM_DATA_FORMAT_RIGHT_16;
    init.ch0ch1_stereo_enable = false;
    init.number_channels = SL_HAL_PDM_NUMBER_OF_CHANNELS_ONE;
  } else if (n_channels == 2) {
    init.data_format = SL_HAL_PDM_DATA_FORMAT_DOUBLE_16;
    init.ch0ch1_stereo_enable = true;
    init.number_channels = SL_HAL_PDM_NUMBER_OF_CHANNELS_TWO;
  }

  sl_hal_pdm_init(PDM, &init);

  status = sl_dma_manager_get_default_handle(&dma_handle);
  if (status != SL_STATUS_OK) {
    return SL_STATUS_FAIL;
  }
  sl_clock_manager_enable_bus_clock(SL_BUS_CLOCK_LDMAXBAR0);
  status = sl_dma_manager_allocate_channel(dma_handle, &dma_channel_id);
  if (status != SL_STATUS_OK) {
    return SL_STATUS_FAIL;
  }

  dma_sequence_no = 0;
  (void)sl_dma_manager_register_channel_irq_callback(dma_handle, dma_channel_id, pdm_dma_irq_cb);

  dma_descriptor[0].xfer.dst_inc  = SL_HAL_LDMA_CTRL_DST_INC_NONE;
  dma_descriptor[0].xfer.size     = SL_HAL_LDMA_CTRL_SIZE_WORD;
  dma_descriptor[0].xfer.done_ifs = 1;
  dma_descriptor[1].xfer.dst_inc  = SL_HAL_LDMA_CTRL_DST_INC_NONE;
  dma_descriptor[1].xfer.size     = SL_HAL_LDMA_CTRL_SIZE_WORD;
  dma_descriptor[1].xfer.done_ifs = 1;

  if (n_channels == 1) {
    dma_descriptor[0].xfer.size = SL_HAL_LDMA_CTRL_SIZE_HALF;
    dma_descriptor[1].xfer.size = SL_HAL_LDMA_CTRL_SIZE_HALF;
  }

#if defined(SL_CATALOG_POWER_MANAGER_PRESENT)
  sl_power_manager_add_em_requirement(SL_POWER_MANAGER_EM1);
#endif

  reading_samples_to_buffer = false;
  streaming_in_progress = false;
  num_channels = n_channels;
  initialized = true;
  mic_running = false;

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    Read samples from the microphone into a buffer
 ******************************************************************************/
sl_status_t sl_mic_get_n_samples(void *buffer, uint32_t n_frames)
{
  if (!initialized) {
    return SL_STATUS_NOT_INITIALIZED;
  }

  if (reading_samples_to_buffer || streaming_in_progress) {
    return SL_STATUS_INVALID_STATE;
  }

  if (!mic_running) {
    sl_mic_start();
  }

  while (!mic_ready) {
  }

  uint32_t first_chunk = n_frames;
  if (first_chunk > MIC_PDM_MAX_XFER) {
    first_chunk = MIC_PDM_MAX_XFER;
  }

  sl_hal_ldma_stop_transfer(LDMA0, dma_channel_id);
  sl_hal_pdm_fifo_flush(PDM);

  sample_buffer = (int16_t *)buffer;
  sample_count = n_frames;
  sample_index = first_chunk;
  reading_samples_to_buffer = true;

  pdm_ldma_start_discard_then_fill(sample_buffer, first_chunk);

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    Start streaming
 ******************************************************************************/
sl_status_t sl_mic_start_streaming(void *buffer, uint32_t n_frames, sl_mic_buffer_ready_callback_t callback)
{
  if (!initialized) {
    return SL_STATUS_NOT_INITIALIZED;
  }

  if (reading_samples_to_buffer || streaming_in_progress) {
    return SL_STATUS_INVALID_STATE;
  }

  if (n_frames > MIC_PDM_MAX_XFER) {
    return SL_STATUS_INVALID_PARAMETER;
  }

  if (!mic_running) {
    sl_mic_start();
  }

  while (!mic_ready) {
  }

  sl_hal_ldma_stop_transfer(LDMA0, dma_channel_id);
  sl_hal_pdm_fifo_flush(PDM);

  sample_count = n_frames;
  sample_index = n_frames;
  streaming_buffer[0] = (int16_t *)buffer;
  streaming_buffer[1] = &(((int16_t *)buffer)[n_frames * num_channels]);
  buffer_ready_callback = callback;
  streaming_in_progress = true;

  pdm_ldma_start_discard_then_fill(streaming_buffer[0], n_frames);

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    De-initialize the microphone
 ******************************************************************************/
sl_status_t sl_mic_deinit(void)
{
  sl_mic_stop();

  sl_hal_pdm_stop(PDM);
  sl_hal_pdm_clear(PDM);
  sl_hal_pdm_fifo_flush(PDM);
  sl_hal_pdm_reset(PDM);

  sl_gpio_set_pin_mode(&pdm_clk_gpio, SL_GPIO_MODE_DISABLED, 0);
  sl_gpio_set_pin_mode(&pdm_din_gpio, SL_GPIO_MODE_DISABLED, 0);

  sl_dma_manager_free_channel(dma_handle, dma_channel_id);

#if defined(SL_CATALOG_POWER_MANAGER_PRESENT)
  sl_power_manager_remove_em_requirement(SL_POWER_MANAGER_EM1);
#endif

  mic_running = false;
  initialized = false;

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    Starts the microphone
 ******************************************************************************/
sl_status_t sl_mic_start(void)
{
  if (!initialized) {
    return SL_STATUS_NOT_INITIALIZED;
  }

  if (mic_running) {
    return SL_STATUS_INVALID_STATE;
  }

  sl_hal_pdm_clear(PDM);
  sl_hal_pdm_fifo_flush(PDM);
  sl_hal_pdm_start(PDM);

  pdm_ldma_start_discard_warmup();

  sl_sleeptimer_start_timer_ms(&mic_wake_up_timer, 15, timeout_callback, NULL, 0, 0);

  mic_running = true;

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    Stops the microphone
 ******************************************************************************/
sl_status_t sl_mic_stop(void)
{
  if (!mic_running) {
    return SL_STATUS_INVALID_STATE;
  }

  sl_hal_ldma_stop_transfer(LDMA0, dma_channel_id);
  (void)sl_sleeptimer_stop_timer(&mic_wake_up_timer);

  sl_hal_pdm_stop(PDM);

  while ((sl_hal_pdm_get_status(PDM) & PDM_STATUS_ACT) == 1U) {
  }

  mic_running = false;
  mic_ready = false;
  reading_samples_to_buffer = false;
  streaming_in_progress = false;

  return SL_STATUS_OK;
}

/***************************************************************************//**
 *    Checks if the sample buffer is ready
 ******************************************************************************/
bool sl_mic_sample_buffer_ready(void)
{
  return (!reading_samples_to_buffer);
}

/***************************************************************************//**
 *    Calculates the dBSPL value for a channel from a sample buffer
 ******************************************************************************/
sl_status_t sl_mic_calculate_sound_level(float *sound_level, const int16_t *buffer, uint32_t n_frames, uint8_t channel)
{
  float sample;
  float power;
  float mean;
  uint32_t i;

  if (channel >= num_channels) {
    return SL_STATUS_INVALID_PARAMETER;
  }

  mean = 0.0f;
  for ( i = channel; i < (n_frames * num_channels); i += num_channels) {
    mean += (float) buffer[i];
  }
  mean = mean / (float) n_frames;

  power = 0;
  for ( i = channel; i < (n_frames * num_channels); i += num_channels) {
    sample = (((float)buffer[i] - mean) / 32767.0f);
    power += sample * sample;
  }
  power = power / (float)n_frames;

  *sound_level = 10.0f * log10f(power) + 120;

  return SL_STATUS_OK;
}

/***************************************************************************//**
 * @brief
 *  DMA operation completion (ping-pong) handler.
 ******************************************************************************/
static bool dma_complete(uint32_t channel,
                         uint32_t sequenceNo,
                         void *userParam)
{
  (void)channel;
  (void)userParam;

  if (reading_samples_to_buffer) {
    /* discard→fill: only the fill descriptor raises DONE. Common case is
     * n_frames <= MAX_XFER so sample_index already equals sample_count. */
    if (sample_index >= sample_count) {
      reading_samples_to_buffer = false;
      /* Keep PDM running; resume discard so the next get_n_samples does not
       * re-settle the filter from cold (matches quiet-room ~48 dBSPL). */
      pdm_ldma_start_discard_warmup();
      return true;
    }

    sl_hal_ldma_descriptor_t *next_desc;
    if (sequenceNo & 0x01) {
      next_desc = &dma_descriptor[0];
    } else {
      next_desc = &dma_descriptor[1];
    }

    next_desc->xfer.dst_inc   = SL_HAL_LDMA_CTRL_DST_INC_ONE;
    next_desc->xfer.dst_addr  = (uint32_t)&sample_buffer[sample_index * num_channels];
    next_desc->xfer.done_ifs  = 1;
    next_desc->xfer.link      = 1;
    next_desc->xfer.link_mode = SL_HAL_LDMA_LINK_MODE_REL;
    next_desc->xfer.link_addr = ((sequenceNo & 0x01) ? 1 : -1)
                                * (int32_t)SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

    if ((sample_count - sample_index) > MIC_PDM_MAX_XFER) {
      next_desc->xfer.xfer_count = (MIC_PDM_MAX_XFER - 1);
      sample_index += MIC_PDM_MAX_XFER;
    } else {
      next_desc->xfer.xfer_count = (sample_count - sample_index) - 1;
      sample_index += (sample_count - sample_index);
    }
  } else if (streaming_in_progress) {
    if (sequenceNo == 0) {
      /* First fill (streaming_buffer[0]) done — switch to ping-pong. */
      dma_descriptor[0].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_ONE;
      dma_descriptor[0].xfer.xfer_count = sample_count - 1;
      dma_descriptor[0].xfer.dst_addr   = (uint32_t)streaming_buffer[1];
      dma_descriptor[0].xfer.done_ifs   = 1;
      dma_descriptor[0].xfer.link       = 1;
      dma_descriptor[0].xfer.link_mode  = SL_HAL_LDMA_LINK_MODE_REL;
      dma_descriptor[0].xfer.link_addr  = 1 * SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

      dma_descriptor[1].xfer.dst_inc    = SL_HAL_LDMA_CTRL_DST_INC_ONE;
      dma_descriptor[1].xfer.xfer_count = sample_count - 1;
      dma_descriptor[1].xfer.dst_addr   = (uint32_t)streaming_buffer[0];
      dma_descriptor[1].xfer.done_ifs   = 1;
      dma_descriptor[1].xfer.link       = 1;
      dma_descriptor[1].xfer.link_mode  = SL_HAL_LDMA_LINK_MODE_REL;
      dma_descriptor[1].xfer.link_addr  = -1 * (int32_t)SL_HAL_LDMA_DESCRIPTOR_NON_EXTEND_SIZE_WORD;

      pdm_ldma_start();

      if (buffer_ready_callback) {
        buffer_ready_callback(streaming_buffer[0], sample_count);
      }
    } else {
      uint32_t idx_next = 1 - (sequenceNo % 2);
      if (buffer_ready_callback) {
        buffer_ready_callback(streaming_buffer[idx_next], sample_count);
      }
    }
  }

  return true;
}

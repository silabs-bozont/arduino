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

#include "MatterDeviceInstanceInfoProvider.h"
#include <silabs_stubs.h>
#include <platform/CHIPDeviceError.h>
#include <platform/PlatformManager.h>
#include <platform/silabs/SilabsConfig.h>
#include <lib/support/CodeUtils.h>
#include <lib/support/CHIPMemString.h>
#include <app/util/af-types.h>
#include <zap-generated/CodeDrivenCallback.h>
#include <cstring>
#include <new>

using namespace chip;
using namespace chip::DeviceLayer;
using SilabsConfig = chip::DeviceLayer::Internal::SilabsConfig;

namespace {

/**
 * Delegates to the Silabs provision DeviceInstanceInfoProvider with Arduino-owned
 * NVM-then-buffer fallbacks for root BasicInformation strings/versions that sketches
 * set via Matter.set_* (factory NVM still wins when present)
 */
class ArduinoMatterDeviceInstanceInfoProvider : public DeviceInstanceInfoProvider
{
public:
  explicit ArduinoMatterDeviceInstanceInfoProvider(DeviceInstanceInfoProvider * base) :
    mBase(base)
  {
  }

  CHIP_ERROR GetVendorName(char * buf, size_t bufSize) override
  {
    return GetNvmStringOrFallback(SilabsConfig::kConfigKey_VendorName, buf, bufSize, arduino_matter_vendor_name);
  }

  CHIP_ERROR GetVendorId(uint16_t & vendorId) override
  {
    return mBase->GetVendorId(vendorId);
  }

  CHIP_ERROR GetProductName(char * buf, size_t bufSize) override
  {
    return GetNvmStringOrFallback(SilabsConfig::kConfigKey_ProductName, buf, bufSize, arduino_matter_product_name);
  }

  CHIP_ERROR GetProductId(uint16_t & productId) override
  {
    return mBase->GetProductId(productId);
  }

  CHIP_ERROR GetPartNumber(char * buf, size_t bufSize) override
  {
    return mBase->GetPartNumber(buf, bufSize);
  }

  CHIP_ERROR GetProductURL(char * buf, size_t bufSize) override
  {
    return mBase->GetProductURL(buf, bufSize);
  }

  CHIP_ERROR GetProductLabel(char * buf, size_t bufSize) override
  {
    return mBase->GetProductLabel(buf, bufSize);
  }

  CHIP_ERROR GetSerialNumber(char * buf, size_t bufSize) override
  {
    return GetNvmStringOrFallback(SilabsConfig::kConfigKey_SerialNum, buf, bufSize, arduino_matter_serial_number);
  }

  CHIP_ERROR GetManufacturingDate(uint16_t & year, uint8_t & month, uint8_t & day) override
  {
    return mBase->GetManufacturingDate(year, month, day);
  }

  CHIP_ERROR GetManufacturingDateSuffix(MutableCharSpan & suffixBuffer) override
  {
    return mBase->GetManufacturingDateSuffix(suffixBuffer);
  }

  CHIP_ERROR GetHardwareVersion(uint16_t & hardwareVersion) override
  {
    CHIP_ERROR err = SilabsConfig::ReadConfigValue(SilabsConfig::kConfigKey_HardwareVersion, hardwareVersion);
    if (err == CHIP_DEVICE_ERROR_CONFIG_NOT_FOUND) {
      hardwareVersion = arduino_matter_hardware_version;
      return CHIP_NO_ERROR;
    }
    return err;
  }

  CHIP_ERROR GetHardwareVersionString(char * buf, size_t bufSize) override
  {
    return GetNvmStringOrFallback(SilabsConfig::kConfigKey_HardwareVersionString, buf, bufSize, arduino_matter_hardware_version_string);
  }

  CHIP_ERROR GetRotatingDeviceIdUniqueId(MutableByteSpan & uniqueIdSpan) override
  {
    return mBase->GetRotatingDeviceIdUniqueId(uniqueIdSpan);
  }

  CHIP_ERROR GetProductFinish(app::Clusters::BasicInformation::ProductFinishEnum * finish) override
  {
    return mBase->GetProductFinish(finish);
  }

  CHIP_ERROR GetProductPrimaryColor(app::Clusters::BasicInformation::ColorEnum * primaryColor) override
  {
    return mBase->GetProductPrimaryColor(primaryColor);
  }

  CHIP_ERROR GetJointFabricMode(uint8_t & jointFabricMode) override
  {
    return mBase->GetJointFabricMode(jointFabricMode);
  }

  CHIP_ERROR GetLocalConfigDisabled(bool & localConfigDisabled) override
  {
    return mBase->GetLocalConfigDisabled(localConfigDisabled);
  }

  CHIP_ERROR SetLocalConfigDisabled(bool localConfigDisabled) override
  {
    return mBase->SetLocalConfigDisabled(localConfigDisabled);
  }

  DeviceInfoCapabilityMinimas GetSupportedCapabilityMinimaValues() override
  {
    return mBase->GetSupportedCapabilityMinimaValues();
  }

private:
  DeviceInstanceInfoProvider * mBase;

  CHIP_ERROR GetNvmStringOrFallback(SilabsConfig::Key key, char * buf, size_t bufSize, const char * fallback) {
    size_t len = 0;
    CHIP_ERROR err = SilabsConfig::ReadConfigValueStr(key, buf, bufSize, len);
    if (err == CHIP_DEVICE_ERROR_CONFIG_NOT_FOUND) {
      VerifyOrReturnError(buf != nullptr, CHIP_ERROR_INVALID_ARGUMENT);
      VerifyOrReturnError(fallback != nullptr, CHIP_ERROR_INVALID_ARGUMENT);
      VerifyOrReturnError(bufSize > strlen(fallback), CHIP_ERROR_BUFFER_TOO_SMALL);
      Platform::CopyString(buf, bufSize, fallback);
      return CHIP_NO_ERROR;
    }
    return err;
  }
};

ArduinoMatterDeviceInstanceInfoProvider * gArduinoProvider = nullptr;

} // namespace

void InstallArduinoMatterDeviceInstanceInfoProvider()
{
  if (gArduinoProvider != nullptr) {
    return;
  }

  DeviceInstanceInfoProvider * base = GetDeviceInstanceInfoProvider();
  if (base == nullptr) {
    return;
  }

  gArduinoProvider = new (std::nothrow) ArduinoMatterDeviceInstanceInfoProvider(base);
  if (gArduinoProvider == nullptr) {
    return;
  }
  SetDeviceInstanceInfoProvider(gArduinoProvider);

  // BasicInformationCluster binds DeviceInstanceInfoProvider by reference in
  // MatterBasicInformationClusterInitCallback (before Arduino setup/begin)
  // Re-init so it captures the wrapper instead of Provision::Storage
  {
    DeviceLayer::StackLock lock;
    MatterBasicInformationClusterShutdownCallback(kRootEndpointId, MatterClusterShutdownType::kClusterShutdown);
    MatterBasicInformationClusterInitCallback(kRootEndpointId);
  }
}

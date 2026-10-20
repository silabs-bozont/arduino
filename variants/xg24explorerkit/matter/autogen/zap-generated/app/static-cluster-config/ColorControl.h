/*
 *
 *    Copyright (c) 2022 Project CHIP Authors
 *
 *    Licensed under the Apache License, Version 2.0 (the "License");
 *    you may not use this file except in compliance with the License.
 *    You may obtain a copy of the License at
 *
 *        http://www.apache.org/licenses/LICENSE-2.0
 *
 *    Unless required by applicable law or agreed to in writing, software
 *    distributed under the License is distributed on an "AS IS" BASIS,
 *    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *    See the License for the specific language governing permissions and
 *    limitations under the License.
 */


// DO NOT EDIT - Generated file
//
// Application configuration for ColorControl based on EMBER configuration
#pragma once

#include <app/util/cluster-config.h>
#include <clusters/ColorControl/AttributeIds.h>
#include <clusters/ColorControl/CommandIds.h>
#include <clusters/ColorControl/Enums.h>

#include <array>

namespace chip {
namespace app {
namespace Clusters {
namespace ColorControl {
namespace StaticApplicationConfig {
namespace detail {
inline constexpr AttributeId kEndpoint2EnabledAttributes[] = {
    Attributes::CurrentHue::Id,
    Attributes::CurrentSaturation::Id,
    Attributes::RemainingTime::Id,
    Attributes::CurrentX::Id,
    Attributes::CurrentY::Id,
    Attributes::ColorTemperatureMireds::Id,
    Attributes::ColorMode::Id,
    Attributes::Options::Id,
    Attributes::NumberOfPrimaries::Id,
    Attributes::EnhancedCurrentHue::Id,
    Attributes::EnhancedColorMode::Id,
    Attributes::ColorLoopActive::Id,
    Attributes::ColorLoopDirection::Id,
    Attributes::ColorLoopTime::Id,
    Attributes::ColorLoopStartEnhancedHue::Id,
    Attributes::ColorLoopStoredEnhancedHue::Id,
    Attributes::ColorCapabilities::Id,
    Attributes::ColorTempPhysicalMinMireds::Id,
    Attributes::ColorTempPhysicalMaxMireds::Id,
    Attributes::CoupleColorTempToLevelMinMireds::Id,
    Attributes::StartUpColorTemperatureMireds::Id,
    Attributes::FeatureMap::Id,
    Attributes::ClusterRevision::Id,
};
inline constexpr CommandId kEndpoint2EnabledCommands[] = {
    Commands::MoveToHue::Id,
    Commands::MoveHue::Id,
    Commands::StepHue::Id,
    Commands::MoveToSaturation::Id,
    Commands::MoveSaturation::Id,
    Commands::StepSaturation::Id,
    Commands::MoveToHueAndSaturation::Id,
    Commands::MoveToColor::Id,
    Commands::MoveColor::Id,
    Commands::StepColor::Id,
    Commands::MoveToColorTemperature::Id,
    Commands::EnhancedMoveToHue::Id,
    Commands::EnhancedMoveHue::Id,
    Commands::EnhancedStepHue::Id,
    Commands::EnhancedMoveToHueAndSaturation::Id,
    Commands::ColorLoopSet::Id,
    Commands::StopMoveStep::Id,
    Commands::MoveColorTemperature::Id,
    Commands::StepColorTemperature::Id,
};
} // namespace detail

using FeatureBitmapType = Feature;

inline constexpr std::array<Clusters::StaticApplicationConfig::ClusterConfiguration<FeatureBitmapType>, 1 + 0> kFixedClusterConfig = { {
    {
        .endpointNumber = 2,
        .featureMap = BitFlags<FeatureBitmapType> {
            FeatureBitmapType::kHueAndSaturation, // feature bit 0x1
            FeatureBitmapType::kEnhancedHue, // feature bit 0x2
            FeatureBitmapType::kColorLoop, // feature bit 0x4
            FeatureBitmapType::kXY, // feature bit 0x8
            FeatureBitmapType::kColorTemperature, // feature bit 0x10
        },
        .enabledAttributes =
            Span<const AttributeId>(detail::kEndpoint2EnabledAttributes),
        .enabledCommands =
            Span<const CommandId>(detail::kEndpoint2EnabledCommands),
    },
} };

// If a specific attribute is supported at all across all endpoint static instantiations
inline constexpr bool IsAttributeEnabledOnSomeEndpoint(AttributeId attributeId) {
  switch (attributeId) {
    case Attributes::CurrentHue::Id:
      return true;
    case Attributes::CurrentSaturation::Id:
      return true;
    case Attributes::RemainingTime::Id:
      return true;
    case Attributes::CurrentX::Id:
      return true;
    case Attributes::CurrentY::Id:
      return true;
    case Attributes::ColorTemperatureMireds::Id:
      return true;
    case Attributes::NumberOfPrimaries::Id:
      return true;
    case Attributes::EnhancedCurrentHue::Id:
      return true;
    case Attributes::ColorLoopActive::Id:
      return true;
    case Attributes::ColorLoopDirection::Id:
      return true;
    case Attributes::ColorLoopTime::Id:
      return true;
    case Attributes::ColorLoopStartEnhancedHue::Id:
      return true;
    case Attributes::ColorLoopStoredEnhancedHue::Id:
      return true;
    case Attributes::ColorTempPhysicalMinMireds::Id:
      return true;
    case Attributes::ColorTempPhysicalMaxMireds::Id:
      return true;
    case Attributes::CoupleColorTempToLevelMinMireds::Id:
      return true;
    case Attributes::StartUpColorTemperatureMireds::Id:
      return true;
    case Attributes::FeatureMap::Id:
      return true;
    case Attributes::ClusterRevision::Id:
      return true;
    default:
      return false;
  }
}

// If a specific command is supported at all across all endpoint static instantiations
inline constexpr bool IsCommandEnabledOnSomeEndpoint(CommandId commandId) {
  switch (commandId) {
    case Commands::MoveToHue::Id:
      return true;
    case Commands::MoveHue::Id:
      return true;
    case Commands::StepHue::Id:
      return true;
    case Commands::MoveToSaturation::Id:
      return true;
    case Commands::MoveSaturation::Id:
      return true;
    case Commands::StepSaturation::Id:
      return true;
    case Commands::MoveToHueAndSaturation::Id:
      return true;
    case Commands::MoveToColor::Id:
      return true;
    case Commands::MoveColor::Id:
      return true;
    case Commands::StepColor::Id:
      return true;
    case Commands::MoveToColorTemperature::Id:
      return true;
    case Commands::EnhancedMoveToHue::Id:
      return true;
    case Commands::EnhancedMoveHue::Id:
      return true;
    case Commands::EnhancedStepHue::Id:
      return true;
    case Commands::EnhancedMoveToHueAndSaturation::Id:
      return true;
    case Commands::ColorLoopSet::Id:
      return true;
    case Commands::StopMoveStep::Id:
      return true;
    case Commands::MoveColorTemperature::Id:
      return true;
    case Commands::StepColorTemperature::Id:
      return true;
    default:
      return false;
  }
}

} // namespace StaticApplicationConfig
} // namespace ColorControl
} // namespace Clusters
} // namespace app
} // namespace chip
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
// Application configuration for LevelControl based on EMBER configuration
#pragma once

#include <app/util/cluster-config.h>
#include <clusters/LevelControl/AttributeIds.h>
#include <clusters/LevelControl/CommandIds.h>
#include <clusters/LevelControl/Enums.h>

#include <array>

namespace chip {
namespace app {
namespace Clusters {
namespace LevelControl {
namespace StaticApplicationConfig {
namespace detail {
inline constexpr AttributeId kEndpoint2EnabledAttributes[] = {
    Attributes::CurrentLevel::Id,
    Attributes::RemainingTime::Id,
    Attributes::MinLevel::Id,
    Attributes::MaxLevel::Id,
    Attributes::CurrentFrequency::Id,
    Attributes::MinFrequency::Id,
    Attributes::MaxFrequency::Id,
    Attributes::Options::Id,
    Attributes::OnOffTransitionTime::Id,
    Attributes::OnLevel::Id,
    Attributes::OnTransitionTime::Id,
    Attributes::OffTransitionTime::Id,
    Attributes::DefaultMoveRate::Id,
    Attributes::StartUpCurrentLevel::Id,
    Attributes::FeatureMap::Id,
    Attributes::ClusterRevision::Id,
};
inline constexpr CommandId kEndpoint2EnabledCommands[] = {
    Commands::MoveToLevel::Id,
    Commands::Move::Id,
    Commands::Step::Id,
    Commands::Stop::Id,
    Commands::MoveToLevelWithOnOff::Id,
    Commands::MoveWithOnOff::Id,
    Commands::StepWithOnOff::Id,
    Commands::StopWithOnOff::Id,
};
} // namespace detail

using FeatureBitmapType = Feature;

inline constexpr std::array<Clusters::StaticApplicationConfig::ClusterConfiguration<FeatureBitmapType>, 1 + 0> kFixedClusterConfig = { {
    {
        .endpointNumber = 2,
        .featureMap = BitFlags<FeatureBitmapType> {
            FeatureBitmapType::kOnOff, // feature bit 0x1
            FeatureBitmapType::kLighting, // feature bit 0x2
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
    case Attributes::CurrentLevel::Id:
      return true;
    case Attributes::RemainingTime::Id:
      return true;
    case Attributes::MinLevel::Id:
      return true;
    case Attributes::MaxLevel::Id:
      return true;
    case Attributes::CurrentFrequency::Id:
      return true;
    case Attributes::MinFrequency::Id:
      return true;
    case Attributes::MaxFrequency::Id:
      return true;
    case Attributes::OnOffTransitionTime::Id:
      return true;
    case Attributes::OnLevel::Id:
      return true;
    case Attributes::OnTransitionTime::Id:
      return true;
    case Attributes::OffTransitionTime::Id:
      return true;
    case Attributes::DefaultMoveRate::Id:
      return true;
    case Attributes::StartUpCurrentLevel::Id:
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
    case Commands::MoveToLevel::Id:
      return true;
    case Commands::Move::Id:
      return true;
    case Commands::Step::Id:
      return true;
    case Commands::Stop::Id:
      return true;
    case Commands::MoveToLevelWithOnOff::Id:
      return true;
    case Commands::MoveWithOnOff::Id:
      return true;
    case Commands::StepWithOnOff::Id:
      return true;
    case Commands::StopWithOnOff::Id:
      return true;
    default:
      return false;
  }
}

} // namespace StaticApplicationConfig
} // namespace LevelControl
} // namespace Clusters
} // namespace app
} // namespace chip
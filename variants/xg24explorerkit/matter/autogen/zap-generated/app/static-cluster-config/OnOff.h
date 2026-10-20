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
// Application configuration for OnOff based on EMBER configuration
#pragma once

#include <app/util/cluster-config.h>
#include <clusters/OnOff/AttributeIds.h>
#include <clusters/OnOff/CommandIds.h>
#include <clusters/OnOff/Enums.h>

#include <array>

namespace chip {
namespace app {
namespace Clusters {
namespace OnOff {
namespace StaticApplicationConfig {
namespace detail {
inline constexpr AttributeId kEndpoint2EnabledAttributes[] = {
    Attributes::OnOff::Id,
    Attributes::GlobalSceneControl::Id,
    Attributes::OnTime::Id,
    Attributes::OffWaitTime::Id,
    Attributes::StartUpOnOff::Id,
    Attributes::FeatureMap::Id,
    Attributes::ClusterRevision::Id,
};
inline constexpr CommandId kEndpoint2EnabledCommands[] = {
    Commands::Off::Id,
    Commands::On::Id,
    Commands::Toggle::Id,
    Commands::OffWithEffect::Id,
    Commands::OnWithRecallGlobalScene::Id,
    Commands::OnWithTimedOff::Id,
};
} // namespace detail

using FeatureBitmapType = Feature;

inline constexpr std::array<Clusters::StaticApplicationConfig::ClusterConfiguration<FeatureBitmapType>, 1 + 0> kFixedClusterConfig = { {
    {
        .endpointNumber = 2,
        .featureMap = BitFlags<FeatureBitmapType> {
            FeatureBitmapType::kLighting, // feature bit 0x1
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
    case Attributes::OnOff::Id:
      return true;
    case Attributes::GlobalSceneControl::Id:
      return true;
    case Attributes::OnTime::Id:
      return true;
    case Attributes::OffWaitTime::Id:
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
    case Commands::Off::Id:
      return true;
    case Commands::On::Id:
      return true;
    case Commands::Toggle::Id:
      return true;
    case Commands::OffWithEffect::Id:
      return true;
    case Commands::OnWithRecallGlobalScene::Id:
      return true;
    case Commands::OnWithTimedOff::Id:
      return true;
    default:
      return false;
  }
}

} // namespace StaticApplicationConfig
} // namespace OnOff
} // namespace Clusters
} // namespace app
} // namespace chip
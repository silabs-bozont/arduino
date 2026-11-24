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
// Application configuration for TimeSynchronization based on EMBER configuration
#pragma once

#include <app/util/cluster-config.h>
#include <clusters/TimeSynchronization/AttributeIds.h>
#include <clusters/TimeSynchronization/CommandIds.h>
#include <clusters/TimeSynchronization/Enums.h>

#include <array>

namespace chip {
namespace app {
namespace Clusters {
namespace TimeSynchronization {
namespace StaticApplicationConfig {
namespace detail {
inline constexpr AttributeId kEndpoint0EnabledAttributes[] = {
    Attributes::UTCTime::Id,
    Attributes::Granularity::Id,
    Attributes::TimeSource::Id,
    Attributes::TimeZone::Id,
    Attributes::DSTOffset::Id,
    Attributes::LocalTime::Id,
    Attributes::TimeZoneDatabase::Id,
    Attributes::TimeZoneListMaxSize::Id,
    Attributes::DSTOffsetListMaxSize::Id,
    Attributes::FeatureMap::Id,
    Attributes::ClusterRevision::Id,
};
inline constexpr CommandId kEndpoint0EnabledCommands[] = {
    Commands::SetUTCTime::Id,
    Commands::SetTimeZone::Id,
    Commands::SetDSTOffset::Id,
};
} // namespace detail

using FeatureBitmapType = Feature;

inline constexpr std::array<Clusters::StaticApplicationConfig::ClusterConfiguration<FeatureBitmapType>, 1 + 0> kFixedClusterConfig = { {
    {
        .endpointNumber = 0,
        .featureMap = BitFlags<FeatureBitmapType> {
            FeatureBitmapType::kTimeZone, // feature bit 0x1
        },
        .enabledAttributes =
            Span<const AttributeId>(detail::kEndpoint0EnabledAttributes),
        .enabledCommands =
            Span<const CommandId>(detail::kEndpoint0EnabledCommands),
    },
} };

// If a specific attribute is supported at all across all endpoint static instantiations
inline constexpr bool IsAttributeEnabledOnSomeEndpoint(AttributeId attributeId) {
  switch (attributeId) {
    case Attributes::UTCTime::Id:
      return true;
    case Attributes::TimeZone::Id:
      return true;
    case Attributes::DSTOffset::Id:
      return true;
    case Attributes::LocalTime::Id:
      return true;
    case Attributes::TimeZoneListMaxSize::Id:
      return true;
    case Attributes::DSTOffsetListMaxSize::Id:
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
    case Commands::SetUTCTime::Id:
      return true;
    case Commands::SetTimeZone::Id:
      return true;
    case Commands::SetDSTOffset::Id:
      return true;
    default:
      return false;
  }
}

} // namespace StaticApplicationConfig
} // namespace TimeSynchronization
} // namespace Clusters
} // namespace app
} // namespace chip
#!/usr/bin/env bash
# Start the Matter HIL OTBR container (HA-style) with the OpenThread RCP.
#
# Usage:
#   ./start_otbr.sh <rcp_serial_port>
#   ./start_otbr.sh /dev/tty.usbmodem0004490513501
#   ./start_otbr.sh /dev/ttyACM0
#
# Or set MATTER_HIL_RCP_PORT instead of passing the port as an argument.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"


prepare_docker_config() {
  # Avoid broken macOS keychain creds helper when missing from PATH (common with Colima).
  local cfg="${HOME}/.docker/config.json"
  local store=""
  if [[ -f "$cfg" ]]; then
    store="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("credsStore") or "")' "$cfg" 2>/dev/null || true)"
  fi
  if [[ -n "$store" ]] && ! command -v "docker-credential-${store}" >/dev/null 2>&1; then
    local tmp
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/matter-hil-docker-config.XXXXXX")"
    python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); c.pop("credsStore",None); c.pop("credStore",None); json.dump(c, open(sys.argv[2],"w"), indent=2)' \
      "$cfg" "$tmp/config.json"
    export DOCKER_CONFIG="$tmp"
    echo "Note: docker-credential-${store} not in PATH; using temporary Docker config without credsStore"
  fi
}

run_compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
  fi
}


usage() {
  echo "Usage: $0 <rcp_serial_port>" >&2
  echo "  e.g. $0 /dev/tty.usbmodemXXXXXXXX" >&2
  echo "  e.g. $0 /dev/ttyACM0" >&2
  echo "" >&2
  echo "Alternatively set MATTER_HIL_RCP_PORT and run without arguments." >&2
}

if ! command -v docker >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  echo "Error: docker not found. Install Docker Engine (Linux) or OrbStack/Colima (macOS)." >&2
  exit 1
fi

# Prefer CLI arg; fall back to env
if [[ $# -ge 1 ]]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Error: unknown option '$1'" >&2
      usage
      exit 1
      ;;
    *)
      MATTER_HIL_RCP_PORT="$1"
      ;;
  esac
fi

if [[ -z "${MATTER_HIL_RCP_PORT:-}" ]]; then
  echo "Error: RCP serial port not provided." >&2
  usage
  exit 1
fi

if [[ ! -e "${MATTER_HIL_RCP_PORT}" ]]; then
  echo "Error: RCP serial device not found: ${MATTER_HIL_RCP_PORT}" >&2
  exit 1
fi

OS="$(uname -s)"
case "${OS}" in
  Linux)
    OVERLAY="docker-compose.linux.yml"
    if [[ -z "${MATTER_HIL_BACKBONE_IF:-}" ]]; then
      # Prefer default-route interface when available
      if command -v ip >/dev/null 2>&1; then
        MATTER_HIL_BACKBONE_IF="$(ip route show default 2>/dev/null | awk '{print $5; exit}')"
      fi
      MATTER_HIL_BACKBONE_IF="${MATTER_HIL_BACKBONE_IF:-eth0}"
      export MATTER_HIL_BACKBONE_IF
      echo "Using backbone interface: ${MATTER_HIL_BACKBONE_IF}"
    fi
    ;;
  Darwin)
    OVERLAY="docker-compose.macos.yml"
    echo "macOS: ensure OrbStack/Colima can see ${MATTER_HIL_RCP_PORT}"
    ;;
  *)
    echo "Error: unsupported OS '${OS}'" >&2
    exit 1
    ;;
esac

export MATTER_HIL_RCP_PORT
export MATTER_HIL_OTBR_BAUD="${MATTER_HIL_OTBR_BAUD:-460800}"
export MATTER_HIL_OTBR_FLOW="${MATTER_HIL_OTBR_FLOW:-0}"

mkdir -p otbr_data

echo "Starting OTBR with RCP ${MATTER_HIL_RCP_PORT} (${OS} overlay)..."
prepare_docker_config
run_compose -f docker-compose.yml -f "${OVERLAY}" up -d

echo "OTBR starting. REST API: http://127.0.0.1:8081"
echo "Web UI:        http://127.0.0.1:8080"

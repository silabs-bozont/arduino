#!/usr/bin/env bash
# Stop the Matter HIL OTBR container.
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


OS="$(uname -s)"
case "${OS}" in
  Linux)  OVERLAY="docker-compose.linux.yml" ;;
  Darwin) OVERLAY="docker-compose.macos.yml" ;;
  *)
    echo "Error: unsupported OS '${OS}'" >&2
    exit 1
    ;;
esac

# DEVICE is required by compose interpolation even for down
export MATTER_HIL_RCP_PORT="${MATTER_HIL_RCP_PORT:-/dev/null}"

prepare_docker_config
run_compose -f docker-compose.yml -f "${OVERLAY}" down
echo "OTBR stopped."

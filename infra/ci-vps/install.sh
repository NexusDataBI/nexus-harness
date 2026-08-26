#!/usr/bin/env bash
# Idempotent provisioner for a dedicated Nexus CI host (self-hosted GitHub runner).
# Does NOT embed tokens, PATs, or host addresses. Safe to commit.
#
# Required env:
#   RUNNER_VERSION          GitHub Actions runner binary version (e.g. 2.321.0)
# Optional env:
#   RUNNER_TOKEN            Registration token (else read silently from stdin)
#   RUNNER_REPO_URL         Private repo URL for registration (required to configure)
#   RUNNER_LABELS           Extra labels (default: self-hosted,nexus-ci)
#   RUNNER_NAME             Runner name (default: hostname)
#
# Usage:
#   sudo RUNNER_VERSION=2.321.0 RUNNER_REPO_URL=https://github.com/ORG/REPO \
#     RUNNER_TOKEN=... ./install.sh
#   # or:
#   printf '%s' "$TOKEN" | sudo RUNNER_VERSION=... RUNNER_REPO_URL=... ./install.sh

set -euo pipefail

NEXUS_USER="nexus-ci"
RUNNER_DIR="/opt/nexus-runner"
DATA_ROOT="/var/lib/nexus-ci"
CACHE_DIR="${DATA_ROOT}/cache"
ARTIFACTS_DIR="${DATA_ROOT}/artifacts"
LOGS_DIR="${DATA_ROOT}/logs"
SERVICE_NAME="nexus-ci"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '%s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "run as root (sudo)"
  fi
}

require_runner_version() {
  if [[ -z "${RUNNER_VERSION:-}" ]]; then
    die "RUNNER_VERSION must be set (GitHub Actions runner release version)"
  fi
}

read_registration_token() {
  # Prefer env; never echo the value. Fall back to silent stdin.
  if [[ -n "${RUNNER_TOKEN:-}" ]]; then
    REG_TOKEN="${RUNNER_TOKEN}"
  elif [[ -n "${GITHUB_RUNNER_TOKEN:-}" ]]; then
    REG_TOKEN="${GITHUB_RUNNER_TOKEN}"
  elif [[ -n "${REGISTRATION_TOKEN:-}" ]]; then
    REG_TOKEN="${REGISTRATION_TOKEN}"
  elif [[ ! -t 0 ]]; then
    # Silent read from stdin (piped token). Do not print.
    IFS= read -r REG_TOKEN || true
  else
    # Interactive: silent prompt (no echo).
    printf 'Registration token (input hidden): ' >&2
    IFS= read -r -s REG_TOKEN
    printf '\n' >&2
  fi
  if [[ -z "${REG_TOKEN:-}" ]]; then
    die "registration token required via RUNNER_TOKEN / GITHUB_RUNNER_TOKEN / REGISTRATION_TOKEN or stdin"
  fi
}

install_os_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    jq \
    git \
    build-essential \
    libicu-dev \
    libssl-dev
}

ensure_nexus_user() {
  # Idempotent: skip when the dedicated system account already exists.
  if id -u nexus-ci >/dev/null 2>&1 || getent passwd nexus-ci >/dev/null 2>&1; then
    log "user nexus-ci already exists — skipping useradd"
  else
    useradd --system --create-home --home-dir "/home/${NEXUS_USER}" \
      --shell /usr/sbin/nologin --user-group "${NEXUS_USER}"
    log "created system user ${NEXUS_USER}"
  fi
}

ensure_directories() {
  # Bounded data plane (literal paths kept for policy visibility / audits).
  mkdir -p /opt/nexus-runner \
    /var/lib/nexus-ci \
    /var/lib/nexus-ci/cache \
    /var/lib/nexus-ci/artifacts \
    /var/lib/nexus-ci/logs
  chown -R "${NEXUS_USER}:${NEXUS_USER}" "${RUNNER_DIR}" "${DATA_ROOT}"
  chmod 0750 /var/lib/nexus-ci /var/lib/nexus-ci/cache /var/lib/nexus-ci/artifacts /var/lib/nexus-ci/logs
  chmod 0750 /opt/nexus-runner
}

check_docker_prerequisites() {
  if ! command -v docker >/dev/null 2>&1; then
    die "docker CLI not found — install Docker Engine (prefer rootless) before provisioning"
  fi
  if ! docker info >/dev/null 2>&1; then
    log "WARN: docker info failed for root — checking rootless hints for ${NEXUS_USER}"
  fi
  # Prefer rootless: look for per-user docker socket under nexus-ci home.
  local rootless_sock="/home/${NEXUS_USER}/.docker/run/docker.sock"
  if [[ -S "${rootless_sock}" ]]; then
    log "rootless docker socket detected at ${rootless_sock}"
  elif [[ -S /var/run/docker.sock ]]; then
    log "WARN: system docker.sock present — prefer rootless for ${NEXUS_USER}; avoid unrestricted socket exposure to jobs when possible"
    # Ensure nexus-ci can talk to docker if using the system daemon (group docker).
    if getent group docker >/dev/null 2>&1; then
      usermod -aG docker "${NEXUS_USER}" || true
    fi
  else
    die "no docker socket found (rootless or system) — configure Docker/rootless first"
  fi
}

install_runner_binary() {
  local version="${RUNNER_VERSION}"
  local arch
  case "$(uname -m)" in
    x86_64|amd64) arch="x64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) die "unsupported architecture: $(uname -m)" ;;
  esac

  local marker="${RUNNER_DIR}/.nexus-runner-version"
  if [[ -x "${RUNNER_DIR}/run.sh" && -f "${marker}" ]] && [[ "$(cat "${marker}")" == "${version}" ]]; then
    log "runner ${version} already installed in ${RUNNER_DIR} — skipping download"
    return 0
  fi

  local tarball="actions-runner-linux-${arch}-${version}.tar.gz"
  local url="https://github.com/actions/runner/releases/download/v${version}/${tarball}"
  local tmp
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '${tmp}'" RETURN

  log "downloading GitHub Actions runner v${version} (${arch})"
  curl -fsSL -o "${tmp}/${tarball}" "${url}"
  # Clear previous binary tree but keep .credentials* if already configured (idempotent re-run of binary only).
  find "${RUNNER_DIR}" -mindepth 1 -maxdepth 1 \
    ! -name '.credentials' ! -name '.credentials_rsaparams' \
    ! -name '.runner' ! -name '.path' \
    -exec rm -rf {} +
  tar -xzf "${tmp}/${tarball}" -C "${RUNNER_DIR}"
  printf '%s\n' "${version}" > "${marker}"
  chown -R "${NEXUS_USER}:${NEXUS_USER}" "${RUNNER_DIR}"
}

configure_runner() {
  if [[ -f "${RUNNER_DIR}/.runner" ]]; then
    log "runner already configured (.runner present) — skipping ./config.sh"
    return 0
  fi
  if [[ -z "${RUNNER_REPO_URL:-}" ]]; then
    die "RUNNER_REPO_URL is required for first-time configuration"
  fi
  local labels="${RUNNER_LABELS:-self-hosted,nexus-ci}"
  local name="${RUNNER_NAME:-$(hostname -s)}"
  # Pass token via env to config.sh without printing it.
  # GitHub config.sh accepts --token; we do not log argv with the secret.
  su -s /bin/bash "${NEXUS_USER}" -c \
    "cd '${RUNNER_DIR}' && ./config.sh --unattended \
      --url '${RUNNER_REPO_URL}' \
      --token '${REG_TOKEN}' \
      --name '${name}' \
      --labels '${labels}' \
      --work '${CACHE_DIR}/_work' \
      --replace"
}

install_systemd_unit() {
  local unit_src="${SCRIPT_DIR}/nexus-ci.service"
  local unit_dst="/etc/systemd/system/${SERVICE_NAME}.service"
  if [[ ! -f "${unit_src}" ]]; then
    die "missing unit file: ${unit_src}"
  fi
  install -m 0644 "${unit_src}" "${unit_dst}"
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}.service"
  systemctl restart "${SERVICE_NAME}.service"
  log "systemd unit ${SERVICE_NAME}.service enabled and started"
}

install_doctor_helper() {
  local doctor_src="${SCRIPT_DIR}/nexus-ci-host-doctor.sh"
  if [[ -f "${doctor_src}" ]]; then
    install -m 0755 "${doctor_src}" /usr/local/bin/nexus-ci-host-doctor
    # Thin alias for `nexus ci-host doctor` until Python summarize_health (Task 7).
    cat >/usr/local/bin/nexus-ci-host <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
case "${cmd}" in
  doctor) shift; exec /usr/local/bin/nexus-ci-host-doctor "$@" ;;
  *)
    printf 'usage: nexus-ci-host doctor\n' >&2
    exit 2
    ;;
esac
EOF
    chmod 0755 /usr/local/bin/nexus-ci-host
  fi
}

main() {
  require_root
  require_runner_version
  read_registration_token
  install_os_packages
  ensure_nexus_user
  ensure_directories
  check_docker_prerequisites
  install_runner_binary
  configure_runner
  install_systemd_unit
  install_doctor_helper
  # Unset so later accidental logs cannot print it.
  unset REG_TOKEN RUNNER_TOKEN GITHUB_RUNNER_TOKEN REGISTRATION_TOKEN
  log "Nexus CI host provisioning complete"
}

main "$@"

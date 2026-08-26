#!/usr/bin/env bash
# Idempotent provisioner for the restricted nexus-deploy identity on a client VM.
# Does NOT embed hostnames, IPs, SSH private keys, or client secrets.
#
# Required env:
#   NEXUS_DEPLOY_PUBKEY   OpenSSH public key text for CI (one line). The key is
#                         restricted with command="/usr/local/bin/nexus-deploy".
# Optional env:
#   NEXUS_DEPLOY_SERVICES_SRC  Path to services.json allowlist to install
#                              (default: ./services.json.example next to this script
#                              if present; otherwise operator must supply later).
#
# Usage (on the client VM as root):
#   sudo NEXUS_DEPLOY_PUBKEY='ssh-ed25519 AAAA... ci-deploy' ./install-deploy-user.sh
#
# Client-specific hostnames, compose paths, and registry credentials stay in the
# project profile / secrets store — never in the Canonical Harness repository.
#
# Docker policy (same as CI VPS): fail closed unless a rootless docker socket
# exists for nexus-deploy. NEVER add the deploy user to the docker group
# (root-equivalent socket access).

set -euo pipefail

NEXUS_USER="nexus-deploy"
INSTALL_BIN="/usr/local/bin/nexus-deploy"
INSTALL_SHELL="/usr/local/bin/nexus-deploy-shell"
LIB_DIR="/usr/local/lib/nexus-deploy"
ETC_DIR="/etc/nexus-deploy"
DATA_DIR="/var/lib/nexus-deploy"
ROOTLESS_SOCK="/home/${NEXUS_USER}/.docker/run/docker.sock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HELPER="${SCRIPT_DIR}/../../src/nexus_harness/deploy_contract.py"

log() { printf '%s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "run as root (sudo)"
  fi
}

require_pubkey() {
  if [[ -z "${NEXUS_DEPLOY_PUBKEY:-}" ]]; then
    die "NEXUS_DEPLOY_PUBKEY must be set (CI OpenSSH public key, one line)"
  fi
  # Reject private key material and multi-line blobs.
  case "${NEXUS_DEPLOY_PUBKEY}" in
    *BEGIN*PRIVATE*KEY*|*BEGIN*OPENSSH*PRIVATE*)
      die "NEXUS_DEPLOY_PUBKEY looks like a private key — refuse"
      ;;
  esac
  # Must look like a single-line public key (type + material).
  if [[ "${NEXUS_DEPLOY_PUBKEY}" == *$'\n'* ]]; then
    die "NEXUS_DEPLOY_PUBKEY must be a single line"
  fi
  if [[ ! "${NEXUS_DEPLOY_PUBKEY}" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh\.com)[[:space:]] ]]; then
    die "NEXUS_DEPLOY_PUBKEY must start with a known OpenSSH key type"
  fi
}

check_docker_prerequisites() {
  if ! command -v docker >/dev/null 2>&1; then
    die "docker CLI not found — install Docker Engine (rootless for ${NEXUS_USER}) before provisioning"
  fi
  # Fail closed: require rootless socket. Never grant the docker group (root-equivalent).
  if [[ -S "${ROOTLESS_SOCK}" ]]; then
    log "rootless docker socket detected at ${ROOTLESS_SOCK}"
    return 0
  fi
  if [[ -S /var/run/docker.sock ]]; then
    log "WARN: system /var/run/docker.sock present — refusing docker group membership for ${NEXUS_USER}"
    die "rootless socket missing at ${ROOTLESS_SOCK} — set up rootless Docker for ${NEXUS_USER}; do not grant the docker group"
  fi
  die "no docker socket found — configure rootless Docker for ${NEXUS_USER} first (expected ${ROOTLESS_SOCK})"
}

ensure_user() {
  # Dedicated wrapper shell (not nologin): OpenSSH command= needs a runnable
  # $SHELL; nexus-deploy-shell only execs the restricted entrypoint.
  if id -u "${NEXUS_USER}" >/dev/null 2>&1 || getent passwd "${NEXUS_USER}" >/dev/null 2>&1; then
    log "user ${NEXUS_USER} already exists — ensuring nexus-deploy-shell"
    usermod -s "${INSTALL_SHELL}" "${NEXUS_USER}" 2>/dev/null || true
  else
    useradd --system --create-home --home-dir "/home/${NEXUS_USER}" \
      --shell "${INSTALL_SHELL}" --user-group "${NEXUS_USER}"
    log "created system user ${NEXUS_USER}"
  fi
}

install_deploy_script() {
  mkdir -p "${LIB_DIR}" "${ETC_DIR}" "${DATA_DIR}"
  if [[ ! -f "${SCRIPT_DIR}/nexus-deploy" ]]; then
    die "missing ${SCRIPT_DIR}/nexus-deploy"
  fi
  if [[ ! -f "${SCRIPT_DIR}/nexus-deploy-shell" ]]; then
    die "missing ${SCRIPT_DIR}/nexus-deploy-shell"
  fi
  if [[ ! -f "${REPO_HELPER}" ]]; then
    die "missing deploy helper ${REPO_HELPER}"
  fi
  # Root-owned deploy entrypoint + shell wrapper + helper (not writable by nexus-deploy).
  install -m 0755 -o root -g root "${SCRIPT_DIR}/nexus-deploy" "${INSTALL_BIN}"
  install -m 0755 -o root -g root "${SCRIPT_DIR}/nexus-deploy-shell" "${INSTALL_SHELL}"
  install -m 0644 -o root -g root "${REPO_HELPER}" "${LIB_DIR}/deploy_contract.py"
  chown root:root "${INSTALL_BIN}" "${INSTALL_SHELL}" "${LIB_DIR}/deploy_contract.py"
  chmod 0755 "${INSTALL_BIN}" "${INSTALL_SHELL}"
  chmod 0644 "${LIB_DIR}/deploy_contract.py"
  chmod 0750 "${ETC_DIR}" "${DATA_DIR}"
  # nexus-deploy may read allowlist + write rollback evidence.
  chown root:"${NEXUS_USER}" "${ETC_DIR}" "${DATA_DIR}"
  log "installed ${INSTALL_BIN}, ${INSTALL_SHELL}, and ${LIB_DIR}/deploy_contract.py"
}

install_services_allowlist() {
  local src="${NEXUS_DEPLOY_SERVICES_SRC:-}"
  if [[ -z "${src}" && -f "${SCRIPT_DIR}/services.json.example" ]]; then
    src="${SCRIPT_DIR}/services.json.example"
  fi
  if [[ -n "${src}" ]]; then
    if [[ ! -f "${src}" ]]; then
      die "NEXUS_DEPLOY_SERVICES_SRC not found: ${src}"
    fi
    install -m 0640 -o root -g "${NEXUS_USER}" "${src}" "${ETC_DIR}/services.json"
    log "installed ${ETC_DIR}/services.json from operator-supplied allowlist"
  else
    log "WARN: no services.json installed — place allowlist at ${ETC_DIR}/services.json before deploy"
  fi
}

install_authorized_keys() {
  local home ssh_dir keys
  home="$(getent passwd "${NEXUS_USER}" | cut -d: -f6)"
  [[ -n "${home}" ]] || die "cannot resolve home for ${NEXUS_USER}"
  ssh_dir="${home}/.ssh"
  keys="${ssh_dir}/authorized_keys"
  mkdir -p "${ssh_dir}"
  # Force the restricted command; disable forwarding / tty / agent tricks.
  # Public key material comes from env at install time — never committed here.
  umask 077
  printf 'command="%s",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty %s\n' \
    "${INSTALL_BIN}" \
    "${NEXUS_DEPLOY_PUBKEY}" > "${keys}"
  chown -R "${NEXUS_USER}:${NEXUS_USER}" "${ssh_dir}"
  chmod 0700 "${ssh_dir}"
  chmod 0600 "${keys}"
  log "wrote restricted authorized_keys (command=${INSTALL_BIN})"
}

main() {
  require_root
  require_pubkey
  check_docker_prerequisites
  install_deploy_script
  ensure_user
  install_services_allowlist
  install_authorized_keys
  log "nexus-deploy restricted identity provisioning complete"
  log "Remember: client hostnames, compose paths, and registry creds stay outside this repo"
  log "Docker: rootless only at ${ROOTLESS_SOCK} — never grant the docker group"
}

main "$@"

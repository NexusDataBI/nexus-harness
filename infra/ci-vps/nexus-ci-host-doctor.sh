#!/usr/bin/env bash
# nexus ci-host doctor — shell health checks for the dedicated CI VPS.
# Python summarize_health lives in Task 7; this is the interim wrapper.
#
# Checks: disk, memory, Docker/rootless, runner dirs/process, outbound GitHub.

set -euo pipefail

NEXUS_USER="nexus-ci"
RUNNER_DIR="/opt/nexus-runner"
DATA_ROOT="/var/lib/nexus-ci"
FAILS=0

ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; FAILS=$((FAILS + 1)); }

check_disk() {
  # Root filesystem free space (warn < 5 GiB, fail < 1 GiB available).
  local avail_kb
  avail_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
  if [[ -z "${avail_kb}" ]]; then
    fail "disk: unable to read df for /"
    return
  fi
  local avail_mib=$((avail_kb / 1024))
  if (( avail_mib < 1024 )); then
    fail "disk: only ${avail_mib} MiB free on /"
  elif (( avail_mib < 5120 )); then
    warn "disk: ${avail_mib} MiB free on / (low)"
  else
    ok "disk: ${avail_mib} MiB free on /"
  fi
  if [[ -d "${DATA_ROOT}" ]]; then
    ok "disk: data root ${DATA_ROOT} present"
  else
    fail "disk: missing ${DATA_ROOT}"
  fi
}

check_memory() {
  local mem_available_kb
  mem_available_kb="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
  if [[ -z "${mem_available_kb}" ]]; then
    # Fallback for non-Linux doctor dry-runs.
    if command -v free >/dev/null 2>&1; then
      local free_out
      free_out="$(free -m | awk '/Mem:/ {print $7}')"
      ok "memory: free reports ${free_out:-?} MiB available"
    else
      fail "memory: cannot read /proc/meminfo or free"
    fi
    return
  fi
  local avail_mib=$((mem_available_kb / 1024))
  if (( avail_mib < 512 )); then
    fail "memory: only ${avail_mib} MiB available"
  elif (( avail_mib < 1024 )); then
    warn "memory: ${avail_mib} MiB available (low)"
  else
    ok "memory: ${avail_mib} MiB available"
  fi
}

check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "docker: CLI not installed"
    return
  fi
  local rootless_sock="/home/${NEXUS_USER}/.docker/run/docker.sock"
  if [[ -S "${rootless_sock}" ]]; then
    if DOCKER_HOST="unix://${rootless_sock}" docker info >/dev/null 2>&1; then
      ok "docker: rootless socket healthy (${rootless_sock})"
    else
      fail "docker: rootless socket present but docker info failed"
    fi
    return
  fi
  if [[ -S /var/run/docker.sock ]]; then
    fail "docker: only system /var/run/docker.sock — rootless required at ${rootless_sock}; do not add ${NEXUS_USER} to group docker"
    return
  fi
  fail "docker: no rootless socket at ${rootless_sock}"
}

check_runner_dirs() {
  if [[ -d "${RUNNER_DIR}" ]]; then
    ok "runner: directory ${RUNNER_DIR} present"
  else
    fail "runner: missing ${RUNNER_DIR}"
  fi
  if [[ -x "${RUNNER_DIR}/run.sh" ]]; then
    ok "runner: run.sh executable"
  else
    fail "runner: ${RUNNER_DIR}/run.sh missing or not executable"
  fi
  for sub in cache artifacts logs; do
    if [[ -d "${DATA_ROOT}/${sub}" ]]; then
      ok "runner: ${DATA_ROOT}/${sub} present"
    else
      fail "runner: missing ${DATA_ROOT}/${sub}"
    fi
  done
}

check_runner_process() {
  if pgrep -u "${NEXUS_USER}" -f 'Runner.Listener|run.sh' >/dev/null 2>&1; then
    ok "runner: process running as ${NEXUS_USER}"
  elif systemctl is-active --quiet nexus-ci.service 2>/dev/null; then
    ok "runner: systemd unit nexus-ci.service is active"
  else
    fail "runner: no Listener/run.sh process for ${NEXUS_USER} and unit inactive"
  fi
}

check_github_connectivity() {
  if ! command -v curl >/dev/null 2>&1; then
    fail "github: curl not installed"
    return
  fi
  # Outbound HTTPS to GitHub API (no auth). Soft-fail on network-restricted hosts.
  if curl -fsS --max-time 10 -o /dev/null https://api.github.com/; then
    ok "github: outbound HTTPS to api.github.com succeeded"
  else
    fail "github: cannot reach api.github.com over HTTPS"
  fi
}

main() {
  printf 'nexus ci-host doctor\n'
  check_disk
  check_memory
  check_docker
  check_runner_dirs
  check_runner_process
  check_github_connectivity
  if (( FAILS > 0 )); then
    printf '\nRESULT: FAIL (%s check(s) failed)\n' "${FAILS}"
    exit 1
  fi
  printf '\nRESULT: PASS\n'
  exit 0
}

main "$@"

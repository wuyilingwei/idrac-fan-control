#!/usr/bin/env bash
# macOS 自启动安装 — LaunchAgent (~/Library/LaunchAgents/).
# 用法:
#   bash install.sh /path/to/install-dir
#
# ⚠️ PLAN §12:未签名二进制可能被 Gatekeeper 拦.
#   首次启动若被拦,执行:
#     xattr -d com.apple.quarantine "${INSTALL_DIR}/idrac-fan-control"
# 卸载:
#   launchctl unload ~/Library/LaunchAgents/io.github.idrac-fan-control.plist
#   rm ~/Library/LaunchAgents/io.github.idrac-fan-control.plist
set -euo pipefail

INSTALL_DIR="${1:-}"
if [[ -z "${INSTALL_DIR}" ]]; then
  echo "usage: bash install.sh /path/to/install-dir" >&2
  exit 2
fi
INSTALL_DIR="$(cd "${INSTALL_DIR}" && pwd -P)"

BIN="${INSTALL_DIR}/idrac-fan-control"
if [[ ! -x "${BIN}" ]]; then
  echo "ERROR: ${BIN} not found or not executable (run pyinstaller build.spec first)" >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}/logs"

PLIST_SRC="$(cd "$(dirname "$0")" && pwd -P)/io.github.idrac-fan-control.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/io.github.idrac-fan-control.plist"

sed "s|{{INSTALL_DIR}}|${INSTALL_DIR}|g" "${PLIST_SRC}" > "${PLIST_DST}"
echo "Wrote ${PLIST_DST}"

# 解除 Gatekeeper 隔离 (二进制非签名).
if xattr -p com.apple.quarantine "${BIN}" >/dev/null 2>&1; then
  echo "Removing quarantine flag..."
  xattr -d com.apple.quarantine "${BIN}" || true
fi

# 卸载旧 + 加载新
launchctl unload "${PLIST_DST}" 2>/dev/null || true
launchctl load -w "${PLIST_DST}"
echo "Loaded LaunchAgent. Status:"
launchctl list | grep idrac-fan-control || true

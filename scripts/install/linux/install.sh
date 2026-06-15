#!/usr/bin/env bash
# Linux 自启动安装 — systemd --user 模式(无头机器首选)。
# 用法:
#   bash install.sh /path/to/install-dir
#
# 行为:
#   1. 把 idrac-fan-control.service 模板里的 {{INSTALL_DIR}} 替换为实际路径。
#   2. 写到 ~/.config/systemd/user/idrac-fan-control.service。
#   3. systemctl --user daemon-reload && enable --now.
# 卸载:
#   systemctl --user disable --now idrac-fan-control
#   rm ~/.config/systemd/user/idrac-fan-control.service
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

UNIT_SRC="$(cd "$(dirname "$0")" && pwd -P)/idrac-fan-control.service"
UNIT_DST_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DST_DIR}"
UNIT_DST="${UNIT_DST_DIR}/idrac-fan-control.service"

sed "s|{{INSTALL_DIR}}|${INSTALL_DIR}|g" "${UNIT_SRC}" > "${UNIT_DST}"
echo "Wrote ${UNIT_DST}"

systemctl --user daemon-reload
systemctl --user enable --now idrac-fan-control.service
echo "Enabled & started. Check: systemctl --user status idrac-fan-control"
echo "Linger (auto-start without login): sudo loginctl enable-linger \"\$USER\""

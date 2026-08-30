#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
APP_PYTHON="${VENV_DIR}/bin/python"

if [[ ! -x "${APP_PYTHON}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

if ! "${APP_PYTHON}" -c "import PySide6" >/dev/null 2>&1; then
  "${APP_PYTHON}" -m pip install -e "${ROOT_DIR}[gui]"
fi

cd "${ROOT_DIR}"

if [[ "$#" -eq 0 && -f "samples/1.mp4" ]]; then
  exec "${APP_PYTHON}" -m videofixie.ui.app --source samples/1.mp4
fi

exec "${APP_PYTHON}" -m videofixie.ui.app "$@"

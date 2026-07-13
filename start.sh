#!/usr/bin/env bash
# One-command deploy/run for bot-tele on PythonAnywhere (or any host).
#
# Always runs from the project root so the relative paths used by the bot
# (Dt/ reference workbook and data/ history store) resolve correctly.
#
# Usage:
#   ./start.sh                   # uses python3.13 by default
#   PYTHON=python3.12 ./start.sh
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3.13}"
VENV_DIR="${VENV_DIR:-venv}"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt
# Install the local package itself (deps already pinned above) so `python -m bot_tele` works.
"$VENV_DIR/bin/pip" install --quiet -e . --no-deps

exec "$VENV_DIR/bin/python" -m bot_tele

#!/bin/bash
set -euo pipefail

PID_FILE=".screener.pid"
CHILD_PID=""

if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" || true)"
    if [ -n "${OLD_PID}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ℹ️  Screener уже запущен (pid=${OLD_PID})"
        exit 0
    fi
fi

echo "$$" > "$PID_FILE"
cleanup() {
    if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
        kill "$CHILD_PID" 2>/dev/null || true
        wait "$CHILD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# Используем локальный python из venv, а не системный pip/python.
VENV_DIR="$(pwd)/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "⚠️  Виртуальное окружение не найдено, запускаю setup.sh..."
    bash setup.sh
fi

if [ -f "display_helper.swift" ] && command -v swiftc >/dev/null 2>&1; then
    if [ ! -x "./display_helper" ] || [ "display_helper.swift" -nt "./display_helper" ]; then
        echo "🛠️  Компиляция display_helper..."
        swiftc display_helper.swift -o display_helper
    fi
fi

# Запускаем приложение
echo "🚀 Запуск Screener..."
"$VENV_PYTHON" -u main.py &
CHILD_PID="$!"
wait "$CHILD_PID"

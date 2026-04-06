#!/usr/bin/env bash
set -euo pipefail

# Перейдем в корень проекта
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Настройки для вашей ЛОКАЛЬНОЙ базы данных
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-teamdoctordb}"

# По умолчанию в вашей ОС пароль может быть пустым, либо postgres
export DB_USER="${DB_USER:-postgres}"      # Укажите вашего юзера
export DB_PASSWORD="${DB_PASSWORD:-}"      # Укажите пароль (если есть)

# Автоматическое создание БД и миграции
export DB_AUTO_CREATE_DATABASE=true
export DB_DDL_AUTO=update

echo "=========================================================="
echo "🚀 Запуск Uvicorn сервера с локальной БД PostgreSQL"
echo "URL базы: postgresql://${DB_USER}:<hidden>@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "=========================================================="

# Запуск сервера
exec uvicorn app.main:app --reload \
  --reload-exclude ".idea/*" \
  --reload-exclude "screenshots/*" \
  --reload-exclude "screener/screenshots/*" \
  --reload-exclude "screener/screener.log" \
  --reload-exclude "screener/.screener.pid"

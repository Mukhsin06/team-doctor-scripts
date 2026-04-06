#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

def main():
    root_dir = Path(__file__).parent.parent
    os.chdir(root_dir)

    # Настройки для локальной базы данных (переопределяют app/config.py)
    os.environ.setdefault("DB_HOST", "127.0.0.1")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_NAME", "teamdoctordb")

    # По умолчанию можете указать свои локальные доступы:
    os.environ.setdefault("DB_USER", "postgres") # Замените на своего пользователя если он другой
    os.environ.setdefault("DB_PASSWORD", "")     # Если есть пароль - укажите его здесь

    # Включаем автоматическое создание БД, если ее нет
    os.environ.setdefault("DB_AUTO_CREATE_DATABASE", "true")
    os.environ.setdefault("DB_DDL_AUTO", "update")

    db_user = os.environ["DB_USER"]
    db_host = os.environ["DB_HOST"]
    db_port = os.environ["DB_PORT"]
    db_name = os.environ["DB_NAME"]

    print("==========================================================")
    print("🚀 Запуск Uvicorn сервера с локальной БД PostgreSQL")
    print(f"URL базы: postgresql://{db_user}:<hidden>@{db_host}:{db_port}/{db_name}")
    print("==========================================================")

    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--reload",
        "--reload-exclude", ".idea/*",
        "--reload-exclude", "screenshots/*",
        "--reload-exclude", "screener/screenshots/*",
        "--reload-exclude", "screener/screener.log",
        "--reload-exclude", "screener/.screener.pid",
    ]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nСервер остановлен")

if __name__ == "__main__":
    main()

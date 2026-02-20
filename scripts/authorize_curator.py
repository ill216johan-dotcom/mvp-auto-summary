#!/usr/bin/env python3
"""
authorize_curator.py — Авторизация куратора в Telegram (один раз).

Создаёт файл сессии, который затем копируется на сервер.
Каждый куратор авторизуется один раз — потом сессия работает вечно.

Использование:
    python3 authorize_curator.py --name masha
    python3 authorize_curator.py --name petya

Результат:
    scripts/session_masha.session   — файл сессии для куратора Маша
    scripts/session_petya.session   — файл сессии для куратора Петя

Скопировать на сервер через WinSCP:
    C:\\Users\\dev\\mvp-autosummary\\scripts\\session_masha.session
    → /root/mvp-auto-summary/scripts/session_masha.session
"""

import asyncio
import sys
import os
import argparse

try:
    import qrcode
except ImportError:
    os.system("pip install qrcode --quiet")

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    print("Устанавливаю telethon...")
    os.system("pip install telethon")
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

API_ID   = 32782815
API_HASH = 'a4c241e64433835b4a335b62520ab005'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


async def authorize(session_file: str, curator_name: str):
    print()
    print("=" * 60)
    print(f"  Авторизация куратора: {curator_name}")
    print(f"  Файл сессии: {session_file}.session")
    print("=" * 60)

    client = TelegramClient(session_file, API_ID, API_HASH)

    async def show_qr(qr_login):
        try:
            import qrcode as qrc
            qr = qrc.QRCode(border=1)
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            print()
            qr.print_ascii(invert=True)
        except Exception:
            print(f"\nQR-ссылка: {qr_login.url}")

        print()
        print("Открой Telegram на телефоне куратора:")
        print("  Настройки → Устройства → Подключить устройство")
        print("Наведи камеру на QR-код выше.")
        print()

    print("\nСпособ входа:")
    print("  1 — QR-код (рекомендуется, не нужен SMS)")
    print("  2 — Номер телефона + SMS-код")
    choice = input("\nВведи 1 или 2: ").strip()

    await client.connect()

    if not await client.is_user_authorized():
        if choice == "2":
            phone = input("Номер телефона куратора (+79...): ").strip()
            await client.send_code_request(phone)
            code = input("Код из Telegram (или SMS): ").strip()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                pwd = input("Пароль двухфакторки: ").strip()
                await client.sign_in(password=pwd)
        else:
            print()
            print("Сейчас появится QR-код.")
            print("КУРАТОР должен сканировать его своим телефоном.")
            print()
            try:
                qr_login = await client.qr_login()
                await show_qr(qr_login)
                try:
                    await qr_login.wait(timeout=120)
                except SessionPasswordNeededError:
                    pwd = input("\nВведи пароль двухфакторной аутентификации куратора: ").strip()
                    await client.sign_in(password=pwd)
                except Exception as e:
                    if "timeout" in str(e).lower():
                        print("\nВремя вышло (2 минуты). Запусти скрипт ещё раз.")
                    else:
                        raise
            except Exception as e:
                print(f"Ошибка QR: {e}")
                await client.disconnect()
                return False

    me = await client.get_me()
    await client.disconnect()

    full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    print()
    print(f"✅ Авторизован: {full_name} (@{me.username or 'нет username'})")
    print()
    print("=" * 60)
    print("СЛЕДУЮЩИЕ ШАГИ:")
    print("=" * 60)
    print()
    print(f"1. Файл сессии создан:")
    print(f"   {session_file}.session")
    print()
    print(f"2. Скопируй его через WinSCP на сервер:")
    print(f"   Локально:  scripts\\session_{curator_name}.session")
    print(f"   На сервер: /root/mvp-auto-summary/scripts/session_{curator_name}.session")
    print()
    print(f"3. Получи список чатов куратора:")
    print(f"   python3 list_telegram_chats.py --session session_{curator_name}")
    print()
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Авторизация куратора в Telegram',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 authorize_curator.py --name masha
  python3 authorize_curator.py --name petya
  python3 authorize_curator.py --name ivan

После авторизации появится файл session_<name>.session
Его нужно скопировать на сервер через WinSCP.
        """
    )
    parser.add_argument(
        '--name', required=True,
        help='Имя куратора латиницей, например: masha, petya, ivan'
    )
    args = parser.parse_args()

    # Проверяем что имя только латиница/цифры/подчёркивание
    name = args.name.strip().lower()
    if not name.replace('_', '').isalnum():
        print(f"\n❌ Имя должно содержать только латиницу, цифры или _")
        print(f"   Правильно: masha, petya, ivan_petrov")
        print(f"   Неправильно: Маша, 'петя иванов', петя")
        sys.exit(1)

    session_file = os.path.join(SCRIPT_DIR, f"session_{name}")

    # Если сессия уже существует — предупредить
    if os.path.exists(session_file + ".session"):
        print(f"\n⚠️  Сессия уже существует: session_{name}.session")
        answer = input("Пересоздать? (y/n): ").strip().lower()
        if answer != 'y':
            print("Отмена.")
            sys.exit(0)
        os.remove(session_file + ".session")

    result = asyncio.run(authorize(session_file, name))
    if not result:
        sys.exit(1)


if __name__ == '__main__':
    main()

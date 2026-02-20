#!/usr/bin/env python3
"""
list_telegram_chats.py — Список Telegram чатов. Вход через QR-код.

Использование:
    python3 list_telegram_chats.py --session session_masha
    python3 list_telegram_chats.py --session session_petya
    python3 list_telegram_chats.py                          # старый режим (mvp_session)
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
    from telethon.tl.types import Chat, Channel, User
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    os.system("pip install telethon")
    from telethon import TelegramClient
    from telethon.tl.types import Chat, Channel, User
    from telethon.errors import SessionPasswordNeededError

API_ID   = 32782815
API_HASH = 'a4c241e64433835b4a335b62520ab005'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(
        description='Список Telegram чатов куратора',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 list_telegram_chats.py --session session_masha
  python3 list_telegram_chats.py --session session_petya
        """
    )
    parser.add_argument(
        '--session', default='mvp_session',
        help='Имя файла сессии без .session (по умолчанию: mvp_session)'
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    SESSION_FILE = os.path.join(SCRIPT_DIR, args.session)
    curator_name = args.session.replace('session_', '')

    print()
    print("=" * 60)
    print(f"  MVP Auto-Summary — Список Telegram чатов")
    print(f"  Куратор: {curator_name}  |  Сессия: {args.session}.session")
    print("=" * 60)

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

    # --- вход через QR (правильный способ через Telethon) ---
    async def qr_callback(qr_login):
        """Вызывается каждый раз когда генерируется новый QR-токен"""
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
        print("Открой Telegram на телефоне:")
        print("  Настройки → Устройства → Подключить устройство")
        print("Наведи камеру на QR-код выше.")
        print()

    print("\nСпособ входа:")
    print("  1 — QR-код (рекомендуется)")
    print("  2 — Номер телефона")
    choice = input("\nВведи 1 или 2: ").strip()

    await client.connect()

    if not await client.is_user_authorized():
        if choice == "2":
            # Вход по телефону
            phone = input("Номер телефона (+79...): ").strip()
            await client.send_code_request(phone)
            code = input("Код из Telegram: ").strip()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                pwd = input("Пароль двухфакторки: ").strip()
                await client.sign_in(password=pwd)
        else:
            # Вход через QR — правильный способ
            print()
            print("Сейчас появится QR-код.")
            print("Сканируй его в Telegram: Настройки → Устройства → Подключить устройство")
            print()
            try:
                qr_login = await client.qr_login()
                # Показываем QR
                await qr_callback(qr_login)
                # Ждём сканирования (встроенное ожидание Telethon)
                # qr_login.wait() сам обновляет QR и ждёт подтверждения
                try:
                    await qr_login.wait(timeout=120)
                except SessionPasswordNeededError:
                    pwd = input("\nВведи пароль двухфакторной аутентификации Telegram: ").strip()
                    await client.sign_in(password=pwd)
                except Exception as e:
                    if "timeout" in str(e).lower():
                        print("Время вышло. Запусти скрипт ещё раз.")
                    else:
                        raise
            except Exception as e:
                print(f"Ошибка QR: {e}")
                await client.disconnect()
                return

    me = await client.get_me()
    print(f"\n✅ Авторизован: {me.first_name} {me.last_name or ''}")
    print("\nЗагружаю список чатов...")

    groups  = []
    private = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            chat_id   = int(f"-100{entity.id}")
            chat_type = "супергруппа" if getattr(entity, 'megagroup', False) else "канал"
            groups.append({'id': chat_id, 'title': dialog.name or '', 'type': chat_type,
                           'username': getattr(entity, 'username', '') or ''})
        elif isinstance(entity, Chat):
            groups.append({'id': -entity.id, 'title': dialog.name or '',
                           'type': 'группа', 'username': ''})
        elif isinstance(entity, User) and not entity.bot:
            private.append({'id': entity.id, 'title': dialog.name or '',
                            'type': 'личный',
                            'username': f"@{entity.username}" if entity.username else ''})

    await client.disconnect()

    # --- Вывод ---
    print()
    print("=" * 70)
    print("ГРУППЫ / СУПЕРГРУППЫ:")
    print("=" * 70)
    for c in sorted(groups, key=lambda x: x['title'].lower()):
        u = f"  (@{c['username']})" if c['username'] else ""
        print(f"  {str(c['id']):<24}  [{c['type']:<12}]  {c['title']}{u}")

    print()
    print("=" * 70)
    print("ЛИЧНЫЕ ПЕРЕПИСКИ:")
    print("=" * 70)
    for c in sorted(private, key=lambda x: x['title'].lower()):
        u = f"  ({c['username']})" if c['username'] else ""
        print(f"  {str(c['id']):<24}  [личный      ]  {c['title']}{u}")

    print()
    print(f"Итого: {len(groups)} групп, {len(private)} личных")

    # Сохраняем список в файл — имя файла включает имя куратора
    out_dir = os.path.join(SCRIPT_DIR, '..', 'exports', 'chats')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f'chats_{curator_name}.txt')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(f"Куратор: {curator_name}\n\n")
        f.write("ГРУППЫ:\n")
        for c in sorted(groups, key=lambda x: x['title'].lower()):
            u = f"  (@{c['username']})" if c['username'] else ""
            f.write(f"  {str(c['id']):<24}  [{c['type']:<12}]  {c['title']}{u}\n")
        f.write("\nЛИЧНЫЕ:\n")
        for c in sorted(private, key=lambda x: x['title'].lower()):
            u = f"  ({c['username']})" if c['username'] else ""
            f.write(f"  {str(c['id']):<24}  [личный      ]  {c['title']}{u}\n")

    print(f"Список сохранён: {out_file}")
    print()
    print("=" * 70)
    print("СЛЕДУЮЩИЕ ШАГИ:")
    print("=" * 70)
    print("Скопируй ID нужного чата и скажи мне:")
    print("  какой ID = какой клиент (номер договора)")
    print()
    print("Для выгрузки чата:")
    print(f"  python3 export_telegram_chat.py --session {args.session} --chat CHAT_ID --lead-id LEAD_ID")


if __name__ == '__main__':
    asyncio.run(main())

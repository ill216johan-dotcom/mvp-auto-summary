#!/usr/bin/env python3
"""
setup_dify_chatbot.py
=====================
Создаёт/обновляет Chatbot-приложение в Dify.ai для кураторов.

Архитектура:
  - Один Chatbot ("ФФ Ассистент Куратора") с системным промптом
  - Подключает ДВА типа Knowledge Base:
      1. Общий датасет (оферта, WMS-инструкция) — для контекста по всем клиентам
      2. Клиентский датасет (per LEAD) — фильтрация происходит через переменные
  - Куратор указывает lead_id в начале разговора, бот ищет только по нужному датасету

Использование:
    python3 setup_dify_chatbot.py --dify-url http://84.252.100.93:8080 --api-key YOUR_KEY
    python3 setup_dify_chatbot.py --list-apps     # Показать существующие приложения
    python3 setup_dify_chatbot.py --list-datasets # Показать датасеты

ВАЖНО: Dify Chatbot с несколькими KB создаётся через UI или через DSL-импорт.
Этот скрипт генерирует DSL-файл для импорта и показывает инструкцию.
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / "n8n-workflows" / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://84.252.100.93:8080")
DIFY_API_KEY  = os.getenv("DIFY_API_KEY", "")


def headers():
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }


def list_apps(base_url: str):
    url = f"{base_url}/v1/apps?limit=100"
    resp = requests.get(url, headers=headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def list_datasets(base_url: str):
    url = f"{base_url}/v1/datasets?limit=100"
    resp = requests.get(url, headers=headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_app_by_name(apps: list, name: str) -> dict | None:
    for app in apps:
        if app.get("name") == name:
            return app
    return None


def create_chatbot(base_url: str, name: str, description: str) -> dict:
    """Создаёт базовое chatbot-приложение."""
    url = f"{base_url}/v1/apps"
    payload = {
        "name": name,
        "description": description,
        "mode": "chat",
        "icon": "🤖",
        "icon_background": "#FFEAD5",
    }
    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_app_model_config(base_url: str, app_id: str, dataset_ids: list[str], system_prompt: str) -> dict:
    """Обновляет конфигурацию модели для chatbot — добавляет датасеты и промпт."""
    url = f"{base_url}/v1/apps/{app_id}/model-config"
    
    # Конфигурация датасетов для Retrieval
    dataset_configs = [
        {
            "dataset": {"enabled": True, "id": ds_id},
            "reranking_enable": False,
            "top_k": 5,
            "score_threshold_enabled": False,
        }
        for ds_id in dataset_ids
    ]
    
    payload = {
        "model": {
            "provider": "zhipuai",
            "name": "glm-4-flash",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.5,
                "top_p": 0.9,
                "max_tokens": 2000,
            }
        },
        "pre_prompt": system_prompt,
        "prompt_type": "simple",
        "dataset_configs": {
            "retrieval_model": "multiple",
            "datasets": dataset_configs,
        },
        "opening_statement": (
            "Привет! Я ассистент кураторов ФФ Платформы.\n\n"
            "Укажи номер договора клиента (например: ФФ-4405) и задай вопрос.\n"
            "Я найду информацию по созвонам, чатам и документам.\n\n"
            "Примеры:\n"
            "• «ФФ-4405 — о чём договорились на прошлой неделе?»\n"
            "• «ФФ-987 — какие открытые вопросы?»\n"
            "• «Что говорится в оферте про возврат товара?»"
        ),
        "suggested_questions": [
            "Покажи последние созвоны с ФФ-4405",
            "Какие нерешённые вопросы у ФФ-987?",
            "Что говорит оферта про сроки хранения?",
        ],
        "suggested_questions_after_answer": {"enabled": True},
        "speech_to_text": {"enabled": False},
        "retriever_resource": {"enabled": True},
        "sensitive_word_avoidance": {"enabled": False},
        "agent_mode": {"enabled": False},
        "file_upload": {"enabled": False},
    }
    
    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


SYSTEM_PROMPT = """Ты — умный ассистент кураторов компании «ФФ Платформа» (фулфилмент).

РОЛЬ: Помогаешь кураторам быстро находить информацию по клиентам.

ДОСТУПНЫЕ ДАННЫЕ (Knowledge Base):
- Транскрипты созвонов с клиентами
- История Telegram-переписки
- Ежедневные саммари по клиентам
- Оферта и регламенты ФФ Платформы
- Инструкции по WMS-системе

КАК РАБОТАТЬ:
1. Клиент идентифицируется по номеру договора: ФФ-XXXX или просто числу (4405, 987)
2. Ищи информацию ТОЛЬКО по указанному клиенту
3. Ссылайся на конкретные даты и источники (созвон 15.02, чат от 20.02)
4. Если информации нет — честно скажи об этом
5. Для вопросов об общих правилах — используй оферту и регламенты

ФОРМАТ ОТВЕТОВ:
- Используй Markdown (заголовки, списки, выделение)
- Конкретные факты с датами
- Если есть action items — выдели их отдельно
- Если видишь риски (недовольство клиента, нерешённые вопросы) — предупреди куратора

ОГРАНИЧЕНИЯ:
- Не выдумывай факты
- Не смешивай данные разных клиентов
- Если вопрос вне компетенции — перенаправь к руководству"""


def generate_dsl_export(datasets: list[dict]) -> dict:
    """Генерирует DSL для импорта в Dify через UI."""
    all_dataset_ids = [ds["id"] for ds in datasets]
    
    return {
        "version": "0.1.3",
        "kind": "app",
        "app": {
            "name": "ФФ Ассистент Куратора",
            "mode": "chat",
            "icon": "🤖",
            "icon_background": "#FFEAD5",
            "description": "RAG-ассистент для кураторов. Ищет по созвонам, чатам и документам клиентов ФФ Платформы.",
        },
        "model_config": {
            "model": {
                "provider": "zhipuai",
                "name": "glm-4-flash",
                "mode": "chat",
                "completion_params": {"temperature": 0.5, "max_tokens": 2000},
            },
            "pre_prompt": SYSTEM_PROMPT,
            "prompt_type": "simple",
            "dataset_configs": {
                "retrieval_model": "multiple",
                "datasets": [
                    {
                        "dataset": {"enabled": True, "id": ds_id},
                        "top_k": 5,
                        "score_threshold_enabled": False,
                    }
                    for ds_id in all_dataset_ids
                ],
            },
            "opening_statement": (
                "Привет! Я ассистент кураторов ФФ Платформы.\n\n"
                "Укажи номер договора клиента (например: **ФФ-4405**) и задай вопрос.\n"
                "Я найду информацию по созвонам, чатам и документам.\n\n"
                "Примеры:\n"
                "• «ФФ-4405 — о чём договорились на прошлой неделе?»\n"
                "• «ФФ-987 — какие открытые вопросы?»\n"
                "• «Что говорится в оферте про возврат товара?»"
            ),
            "suggested_questions": [
                "Покажи последние созвоны с ФФ-4405",
                "Какие нерешённые вопросы у ФФ-987?",
                "Что говорит оферта про сроки хранения?",
            ],
            "suggested_questions_after_answer": {"enabled": True},
            "retriever_resource": {"enabled": True},
            "sensitive_word_avoidance": {"enabled": False},
            "file_upload": {"enabled": False},
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Setup Dify Chatbot for curators")
    parser.add_argument("--dify-url",    default=DIFY_BASE_URL)
    parser.add_argument("--api-key",     default=DIFY_API_KEY)
    parser.add_argument("--list-apps",   action="store_true", help="Показать приложения")
    parser.add_argument("--list-datasets", action="store_true", help="Показать датасеты")
    parser.add_argument("--gen-dsl",     action="store_true", help="Сгенерировать DSL для импорта")
    parser.add_argument("--create",      action="store_true", help="Создать chatbot через API")
    args = parser.parse_args()

    base_url = args.dify_url.rstrip("/")
    global DIFY_API_KEY
    DIFY_API_KEY = args.api_key or DIFY_API_KEY

    if not DIFY_API_KEY:
        print("ERROR: DIFY_API_KEY не задан.")
        sys.exit(1)

    if args.list_apps:
        apps = list_apps(base_url)
        print(f"\nПриложений в Dify: {len(apps)}")
        for app in apps:
            print(f"  [{app.get('mode','?')}] {app['name']} → id={app['id']}")
        return

    if args.list_datasets:
        datasets = list_datasets(base_url)
        print(f"\nДатасетов в Dify: {len(datasets)}")
        for ds in datasets:
            doc_count = ds.get('document_count', '?')
            print(f"  {ds['name']} → id={ds['id']} (docs: {doc_count})")
        return

    # Загружаем датасеты
    print(f"\n[Dify] Загружаем датасеты из {base_url} ...")
    datasets = list_datasets(base_url)
    print(f"  Найдено: {len(datasets)}")

    if args.gen_dsl:
        dsl = generate_dsl_export(datasets)
        dsl_path = Path(__file__).parent.parent / "dify-chatbot-app.yaml"
        import yaml
        try:
            with open(dsl_path, "w", encoding="utf-8") as f:
                yaml.dump(dsl, f, allow_unicode=True, default_flow_style=False, indent=2)
            print(f"\nDSL сохранён в: {dsl_path}")
        except ImportError:
            dsl_path_json = Path(__file__).parent.parent / "dify-chatbot-app.json"
            with open(dsl_path_json, "w", encoding="utf-8") as f:
                json.dump(dsl, f, ensure_ascii=False, indent=2)
            print(f"\nDSL (JSON) сохранён в: {dsl_path_json}")
        
        print("\nИнструкция по импорту в Dify:")
        print("  1. Открой http://84.252.100.93:8080")
        print("  2. Studio → Import from DSL file")
        print(f"  3. Загрузи файл: {dsl_path}")
        return

    if args.create:
        # Создаём через API
        all_dataset_ids = [ds["id"] for ds in datasets]
        
        # Проверяем существование
        apps = list_apps(base_url)
        existing = get_app_by_name(apps, "ФФ Ассистент Куратора")
        
        if existing:
            app_id = existing["id"]
            print(f"\n[EXIST] Приложение найдено: {app_id}")
        else:
            print("\n[CREATE] Создаём приложение 'ФФ Ассистент Куратора' ...")
            try:
                app = create_chatbot(base_url, "ФФ Ассистент Куратора",
                                     "RAG-ассистент для кураторов ФФ Платформы")
                app_id = app["id"]
                print(f"  Создано: id={app_id}")
            except Exception as e:
                print(f"ERROR при создании: {e}")
                print("\nВозможно API не поддерживает создание через endpoint /v1/apps.")
                print("Используй --gen-dsl для генерации файла импорта.")
                sys.exit(1)

        # Обновляем конфигурацию
        print(f"\n[CONFIG] Обновляем конфигурацию модели (датасетов: {len(all_dataset_ids)}) ...")
        try:
            update_app_model_config(base_url, app_id, all_dataset_ids, SYSTEM_PROMPT)
            print("  OK!")
        except Exception as e:
            print(f"  WARN: {e}")
            print("  Обнови конфигурацию вручную через UI.")

        print(f"\nГотово! Chatbot URL: {base_url}/chat/{app_id}")
        return

    # По умолчанию — показываем инструкцию
    print("\n" + "="*60)
    print("Дальнейшие шаги для настройки Dify Chatbot:")
    print("="*60)
    print("\n1. Создай датасеты (если ещё не создано):")
    print("   python3 scripts/setup_dify_datasets.py --api-key YOUR_KEY")
    print("\n2. Создай Chatbot через API:")
    print("   python3 scripts/setup_dify_chatbot.py --create --api-key YOUR_KEY")
    print("\n   ИЛИ сгенерируй DSL для ручного импорта:")
    print("   python3 scripts/setup_dify_chatbot.py --gen-dsl --api-key YOUR_KEY")
    print("\n3. В Dify UI (http://84.252.100.93:8080):")
    print("   - Открой приложение 'ФФ Ассистент Куратора'")
    print("   - Проверь подключённые Knowledge Base")
    print("   - Нажми 'Publish' для публикации")
    print("\n4. Добавь ссылку на чат в дайджест Telegram:")
    print("   http://84.252.100.93:8080/chat/APP_ID")
    print("="*60)


if __name__ == "__main__":
    main()

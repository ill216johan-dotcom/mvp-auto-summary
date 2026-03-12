"""
Run full historical Bitrix24 sync + summaries.
Execute inside orchestrator container:
  docker exec mvp-auto-summary-orchestrator-1 python /scripts/run_historical_sync.py
"""
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

sys.path.insert(0, "/app")

from app.config import get_settings
from app.tasks.bitrix_sync import run_bitrix_sync
from app.tasks.bitrix_summary import generate_bitrix_summaries
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.dify_api import DifyClient

s = get_settings()

dsn = (
    f"postgresql://{s.postgres_user}:{s.postgres_password}"
    f"@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}"
)
db = Database(dsn=dsn)
llm = LLMClient(api_key=s.llm_api_key, base_url=s.llm_base_url, model=s.llm_model)
dify = DifyClient(api_key=s.dify_api_key, base_url=s.dify_base_url)

# ---- Step 1: Sync all CRM data from Bitrix ----
print("=" * 60)
print("STEP 1: Syncing CRM data from Bitrix24...")
print("=" * 60)
sync_result = run_bitrix_sync(
    db, llm, dify,
    s.bitrix_webhook_url,
    s.bitrix_contract_field,
    s.transcribe_url,
)
print(json.dumps(sync_result, indent=2, default=str))

# ---- Step 2: Generate historical summaries (all dates) ----
print("=" * 60)
print("STEP 2: Generating historical summaries (all dates)...")
print("=" * 60)
summary_result = generate_bitrix_summaries(db, llm, dify, target_date=None)
print(json.dumps(summary_result, indent=2, default=str))

print("=" * 60)
print("DONE.")

#!/usr/bin/env python3
"""
Диагностика и исправление проблем с WF03 (individual_summary).

Проверяет:
1. Статус файлов в processed_files
2. Есть ли unprocessed calls
3. Запускает WF03 вручную если нужно
4. Проверяет Dify dataset
"""
import sys
import os
from pathlib import Path
from datetime import date, datetime
import paramiko

sys.path.insert(0, str(Path(__file__).parent.parent))

# SSH config
HOST = "84.252.100.93"
USER = "root"
PASSWORD = "xe1ZlW0Rpiyk"


def run_ssh(cmd: str) -> str:
    """Execute command on VPS."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        if error and not output:
            return f"STDERR: {error}"
        return output
    finally:
        client.close()


def check_processed_files():
    """Check today's processed files status."""
    print("\n" + "="*60)
    print("📊 CHECKING PROCESSED FILES (TODAY)")
    print("="*60)
    
    cmd = """docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT id, lead_id, filename, status, dify_doc_id IS NOT NULL as has_summary, created_at FROM processed_files WHERE DATE(created_at) = CURRENT_DATE ORDER BY created_at;" """
    
    result = run_ssh(cmd)
    print(result)


def check_unprocessed_calls():
    """Check calls that need summarization."""
    print("\n" + "="*60)
    print("📋 CHECKING UNPROCESSED CALLS (NEED SUMMARY)")
    print("="*60)
    
    cmd = """docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT id, lead_id, filename, status FROM processed_files WHERE status = 'completed' AND transcript_text IS NOT NULL AND (dify_doc_id IS NULL OR dify_doc_id = '') ORDER BY created_at DESC LIMIT 10;" """
    
    result = run_ssh(cmd)
    print(result)


def check_client_summaries():
    """Check client_summaries table."""
    print("\n" + "="*60)
    print("📝 CHECKING CLIENT_SUMMARIES TABLE")
    print("="*60)
    
    cmd = """docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT COUNT(*) as total, DATE(summary_date) as date FROM client_summaries GROUP BY DATE(summary_date) ORDER BY date DESC LIMIT 7;" """
    
    result = run_ssh(cmd)
    print(result)


def check_dify_mapping():
    """Check lead_chat_mapping with Dify dataset IDs."""
    print("\n" + "="*60)
    print("🔗 CHECKING DIFY DATASET MAPPING")
    print("="*60)
    
    cmd = """docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT lead_id, lead_name, dify_dataset_id, active FROM lead_chat_mapping WHERE active = true ORDER BY lead_id;" """
    
    result = run_ssh(cmd)
    print(result)


def trigger_wf03_manually():
    """Trigger WF03 manually via API."""
    print("\n" + "="*60)
    print("🚀 TRIGGERING WF03 MANUALLY")
    print("="*60)
    
    # Option 1: Try to call the Python task directly
    cmd = """docker exec mvp-auto-summary-orchestrator-1 python -c "from app.main import app; from app.tasks.individual_summary import IndividualSummaryTask; from app.core.db import Database; from app.core.llm import LLMClient; from app.core.dify_api import DifyClient; from app.config import get_settings; s = get_settings(); db = Database(s.database_dsn); llm = LLMClient(s.llm_api_key, s.llm_base_url, s.llm_model); dify = DifyClient(s.dify_api_key, s.dify_base_url); task = IndividualSummaryTask(db, llm, dify, s.summaries_dir, s.summaries_base_url); result = task.run(); print(f'Result: {result}')" 2>&1 """
    
    print("Running WF03 manually...")
    result = run_ssh(cmd)
    print(result)


def check_orchestrator_logs():
    """Check recent orchestrator logs for WF03."""
    print("\n" + "="*60)
    print("📄 CHECKING ORCHESTRATOR LOGS (WF03)")
    print("="*60)
    
    cmd = "docker logs mvp-auto-summary-orchestrator-1 2>&1 | grep -E 'WF03|individual_summary' | tail -10"
    
    result = run_ssh(cmd)
    print(result if result.strip() else "No WF03 entries found in logs")


def check_container_uptime():
    """Check when orchestrator container started."""
    print("\n" + "="*60)
    print("⏰ ORCHESTRATOR CONTAINER UPTIME")
    print("="*60)
    
    cmd = "docker inspect mvp-auto-summary-orchestrator-1 --format '{{.State.StartedAt}}'"
    
    started_at = run_ssh(cmd).strip()
    print(f"Started at: {started_at}")
    
    # Parse and show human-readable
    try:
        dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        uptime = now - dt
        print(f"Uptime: {uptime}")
    except:
        pass


def main():
    print("🔍 MVP AUTO-SUMMARY DIAGNOSTICS")
    print(f"📅 Date: {date.today()}")
    
    try:
        check_container_uptime()
        check_processed_files()
        check_unprocessed_calls()
        check_client_summaries()
        check_dify_mapping()
        check_orchestrator_logs()
        # Provide instructions for manual trigger
        print("\n" + "="*60)
        print("💡 To trigger WF03 manually, run:"          )
        print("   python scripts/trigger_wf03_now.py"      )
        print("="*60)
        
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

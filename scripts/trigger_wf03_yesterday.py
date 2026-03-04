#!/usr/bin/env python3
"""
Trigger WF03 for YESTERDAY'S date (2026-03-04).
"""
import paramiko
import sys

HOST = "84.252.100.93"
USER = "root"
PASSWORD = "xe1ZlW0Rpiyk"


def run_ssh(cmd: str) -> tuple[str, str]:
    """Execute command on VPS."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
        return stdout.read().decode('utf-8'), stderr.read().decode('utf-8')
    finally:
        client.close()


def main():
    print("="*60)
    print("TRIGGERING WF03 FOR YESTERDAY (2026-03-04)")
    print("="*60)
    
    # Command with explicit date parameter
    cmd = """docker exec mvp-auto-summary-orchestrator-1 python -c "
import sys
sys.path.insert(0, '/app')
from datetime import date
from app.tasks.individual_summary import IndividualSummaryTask
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.dify_api import DifyClient
from app.config import get_settings

print('Loading settings...')
s = get_settings()

print('Connecting to DB...')
db = Database(s.database_dsn)

print('Initializing LLM client...')
llm = LLMClient(s.llm_api_key, s.llm_base_url, s.llm_model)

print('Initializing Dify client...')
dify = DifyClient(s.dify_api_key, s.dify_base_url)

print('Creating WF03 task...')
task = IndividualSummaryTask(
    db=db, 
    llm=llm, 
    dify=dify, 
    summaries_dir=s.summaries_dir,
    summaries_base_url=s.summaries_base_url
)

target_date = date(2026, 3, 4)
print(f'Running WF03 for {target_date}...')
result = task.run(target_date)
print(f'Result: {result}')

db.close()
dify.close()
print('Done!')
" 2>&1"""
    
    print(f"\nRunning command on {HOST}...")
    print("(processing 2026-03-04 files)\n")
    
    stdout, stderr = run_ssh(cmd)
    
    if stdout:
        print("OUTPUT:")
        print(stdout)
    
    if stderr:
        print("\nSTDERR:")
        print(stderr)
    
    print("\n" + "="*60)
    print("Check results above!")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

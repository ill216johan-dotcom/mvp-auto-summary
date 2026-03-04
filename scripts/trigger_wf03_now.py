#!/usr/bin/env python3
"""
Trigger WF03 (individual_summary) manually via SSH.
Processes all unprocessed calls and pushes to Dify.
"""
import paramiko
import sys

HOST = "84.252.100.93"
USER = "root"
PASSWORD = "xe1ZlW0Rpiyk"


def run_ssh(cmd: str) -> tuple[str, str]:
    """Execute command on VPS, return (stdout, stderr)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=300)  # 5 min timeout
        out = stdout.read().decode('utf-8')
        err = stderr.read().decode('utf-8')
        return out, err
    finally:
        client.close()


def main():
    print("="*60)
    print("TRIGGERING WF03 (individual_summary) MANUALLY")
    print("="*60)
    
    # Command to trigger WF03
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

print('Running WF03 for today...')
result = task.run(date.today())
print(f'Result: {result}')

db.close()
dify.close()
print('Done!')
" 2>&1"""
    
    print(f"\nRunning command on {HOST}...")
    print("(this may take 1-2 minutes)\n")
    
    stdout, stderr = run_ssh(cmd)
    
    if stdout:
        print("OUTPUT:")
        print(stdout)
    
    if stderr:
        print("\nSTDERR:")
        print(stderr)
    
    print("\n" + "="*60)
    print("WF03 execution completed!")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

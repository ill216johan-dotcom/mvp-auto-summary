#!/usr/bin/env python3
"""Deploy transcribe service fix via SFTP."""

import os
import paramiko

HOST = os.getenv("SSH_HOST", "")
USER = os.getenv("SSH_USER", "root")
PASSWORD = os.getenv("SSH_PASSWORD", "")

# Files to upload (local -> remote)
FILES_TO_UPLOAD = {
    "C:/Projects/mvp-auto-summary/services/transcribe/transcribe_server.py": "/root/mvp-auto-summary/services/transcribe/transcribe_server.py",
    "C:/Projects/mvp-auto-summary/app/core/db.py": "/root/mvp-auto-summary/app/core/db.py",
    "C:/Projects/mvp-auto-summary/docker-compose.yml": "/root/mvp-auto-summary/docker-compose.yml",
}

# Connect and upload
if not HOST or not PASSWORD:
    raise RuntimeError("SSH_HOST and SSH_PASSWORD must be set in env")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

sftp = client.open_sftp()

# Upload files
for local_path, remote_path in FILES_TO_UPLOAD.items():
    with open(local_path, "r", encoding="utf-8") as f:
        local_content = f.read()
    with sftp.file(remote_path, "w") as f:
        f.write(local_content)
    print(f"Uploaded: {remote_path}")

sftp.close()

# Rebuild and restart
commands = [
    "cd /root/mvp-auto-summary && docker compose build transcribe 2>&1 | tail -5",
    "cd /root/mvp-auto-summary && docker compose build orchestrator 2>&1 | tail -5",
    "cd /root/mvp-auto-summary && docker compose up -d transcribe orchestrator 2>&1",
    "docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep -E 'transcribe|orchestrator'"
]

for cmd in commands:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"\n> {cmd[:50]}...")
    if out: print(out)
    if err: print(f"ERR: {err}")

client.close()
print("\nDeploy complete!")

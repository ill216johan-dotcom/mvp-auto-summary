#!/usr/bin/env python3
"""
SSH helper script for MVP server connections.
Credentials stored in docs/CREDENTIALS.md
"""
import sys
import paramiko

HOST = "84.252.100.93"
USER = "root"
PASSWORD = "xe1ZlW0Rpiyk"


def run_command(cmd: str) -> str:
    """Execute command on MVP server and return output."""
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ssh_cmd.py 'command to run'")
        sys.exit(1)
    
    cmd = " ".join(sys.argv[1:])
    print(run_command(cmd))

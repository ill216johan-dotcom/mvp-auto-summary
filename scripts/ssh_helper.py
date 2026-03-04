#!/usr/bin/env python3
"""SSH helper with password authentication for MVP server diagnostics."""

import os
from typing import TypedDict

import paramiko

HOST = os.getenv("SSH_HOST", "")
USER = os.getenv("SSH_USER", "root")
PASSWORD = os.getenv("SSH_PASSWORD", "")

class CommandResult(TypedDict):
    stdout: str
    stderr: str
    exit_code: int


def run_ssh_commands(commands: list[str]) -> dict[str, CommandResult]:
    """Execute commands via SSH and return results."""
    if not HOST or not PASSWORD:
        raise RuntimeError("SSH_HOST and SSH_PASSWORD must be set in env")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    results = {}
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
        
        for cmd in commands:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
            results[cmd] = {
                "stdout": stdout.read().decode("utf-8", errors="replace"),
                "stderr": stderr.read().decode("utf-8", errors="replace"),
                "exit_code": stdout.channel.recv_exit_status()
            }
        
        # Install SSH key for future passwordless access
        pub_key = open("C:/Users/User/.ssh/mvp_server.pub").read().strip()
        client.exec_command(f'mkdir -p ~/.ssh && echo "{pub_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys', timeout=10)
        
    finally:
        client.close()
    
    return results

if __name__ == "__main__":
    commands = [
        "docker logs mvp-auto-summary-transcribe-1 --tail 10 2>&1 | LANG=C tr -cd '\\11\\12\\15\\40-\\176'"
    ]
    
    results = run_ssh_commands(commands)
    
    for cmd, result in results.items():
        print(f"\n{'='*60}")
        print(f"CMD: {cmd[:60]}...")
        print('='*60)
        if result["stdout"]:
            print(result["stdout"])
        if result["stderr"] and "warning" not in result["stderr"].lower():
            print(f"STDERR: {result['stderr']}")

#!/usr/bin/env python3
"""Install project dependencies"""

import subprocess
import sys

packages = [
    'Flask==3.0.0',
    'Flask-SocketIO==5.3.6', 
    'python-socketio==5.9.0',
    'requests',
    'python-dotenv'
]

print("Installing packages...")
for package in packages:
    print(f"\n>>> Installing {package}...")
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', package, '--timeout', '120'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✓ {package} installed successfully")
    else:
        print(f"✗ Failed to install {package}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")

print("\n\nVerifying installations...")
result = subprocess.run(
    [sys.executable, '-m', 'pip', 'list'],
    capture_output=True,
    text=True
)

if 'Flask' in result.stdout:
    print("✓ Flask is installed!")
    print(result.stdout)
else:
    print("✗ Installation verification failed")

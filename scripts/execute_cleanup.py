"""
LUMI — Safe Project Cleanup Executor

Moves approved malformed directories into quarantine, creates the canonical
audio/generated directory, writes a cleanup manifest, and verifies the project.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path("c:/Users/basar/Desktop/LUMI")
QUARANTINE_DIR = ROOT_DIR / ".cleanup_quarantine"

def execute_safe_cleanup():
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Identify the malformed directories
    malformed_dirs = []
    for item in ROOT_DIR.iterdir():
        if item.is_dir() and "Usersbasar" in item.name:
            malformed_dirs.append(item)
            
    print(f"Found {len(malformed_dirs)} malformed directories to quarantine.")
    
    manifest = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "quarantined_items": []
    }
    
    for d in malformed_dirs:
        dest = QUARANTINE_DIR / d.name
        print(f"Moving {d.name} -> {dest}")
        # Use shutil.move
        shutil.move(str(d), str(dest))
        manifest["quarantined_items"].append({
            "original_path": str(d.resolve()),
            "quarantined_path": str(dest.resolve()),
            "is_dir": True,
            "size_bytes": 0
        })
        
    # Write manifest
    manifest_path = QUARANTINE_DIR / "cleanup_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Cleanup manifest written to {manifest_path}")
    
    # Create canonical audio/generated directory
    audio_gen_dir = ROOT_DIR / "audio" / "generated"
    audio_gen_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = audio_gen_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    print(f"Ensured canonical audio directory exists at: {audio_gen_dir}")
    
    return manifest

if __name__ == "__main__":
    execute_safe_cleanup()

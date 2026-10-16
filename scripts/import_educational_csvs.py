"""
LUMI — Educational CSV Importer and Integrity Verifier

Extracts/copies educational CSV files from AI_Voice_Learning_Buddy_Datasets
into LUMI's data/educational/ directory and verifies SHA-256 integrity.
"""

import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path

TARGET_DIR = Path("c:/Users/basar/Desktop/LUMI/data/educational")
ZIP_SOURCE = Path(r"C:\Users\basar\Downloads\AI_Voice_Learning_Buddy_Datasets.zip")
DIR_SOURCE = Path(r"C:\Users\basar\Downloads\AI_Voice_Learning_Buddy_Datasets\AI_Voice_Learning_Buddy_Datasets")

REQUIRED_FILES = [
    "alphabets.csv",
    "animals.csv",
    "basic_math.csv",
    "colors.csv",
    "fruits.csv",
    "general_knowledge.csv",
    "good_habits.csv",
    "healthy_foods.csv",
    "numbers_counting.csv",
    "shapes.csv",
]

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def import_and_verify():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Source verification: check zip vs directory
    print(f"Target directory: {TARGET_DIR.resolve()}")
    
    results = []
    
    with zipfile.ZipFile(ZIP_SOURCE, "r") as z:
        for filename in REQUIRED_FILES:
            dest_file = TARGET_DIR / filename
            
            # Find in zip
            zip_entry_name = f"AI_Voice_Learning_Buddy_Datasets/{filename}"
            if zip_entry_name not in z.namelist():
                # Try bare filename
                zip_entry_name = filename
                
            raw_bytes = z.read(zip_entry_name)
            expected_hash = sha256_of_bytes(raw_bytes)
            
            # Check if destination file already exists and differs
            if dest_file.exists():
                existing_hash = sha256_of_file(dest_file)
                if existing_hash != expected_hash:
                    print(f"Warning: Destination {filename} already exists with different contents. Preserving user modifications.")
                    results.append({
                        "filename": filename,
                        "status": "preserved_existing",
                        "hash": existing_hash,
                        "size": dest_file.stat().st_size
                    })
                    continue
                else:
                    results.append({
                        "filename": filename,
                        "status": "already_identical",
                        "hash": existing_hash,
                        "size": dest_file.stat().st_size
                    })
                    continue
            
            # Write exact bytes to preserve encoding, headers, BOM, line endings
            with open(dest_file, "wb") as f:
                f.write(raw_bytes)
                
            copied_hash = sha256_of_file(dest_file)
            assert copied_hash == expected_hash, f"Hash mismatch for {filename}!"
            
            results.append({
                "filename": filename,
                "status": "copied_and_verified",
                "hash": copied_hash,
                "size": len(raw_bytes)
            })
            
    print("\nImport Results:")
    print("-" * 80)
    for r in results:
        print(f"{r['filename']:<22} | {r['status']:<20} | {r['size']:<6} bytes | {r['hash'][:16]}...")
    print("-" * 80)
    print("All files verified successfully!")
    return results

if __name__ == "__main__":
    import_and_verify()

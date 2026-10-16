"""
LUMI — Robust JIBO Kids Downloader & Extractor

Downloads split archive parts from GitHub Releases (with Zenodo fallback),
supporting HTTP Range resume, exponential backoff retries, concatenation into combined.zip,
and extraction into datasets/Jibo_Kids/data/.
"""

import os
import sys
import time
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

DATASET_DIR = Path("c:/Users/basar/Desktop/LUMI/datasets/Jibo_Kids")

URLS = {
    "jibo_release_part_aa": [
        "https://github.com/balaji1312/Jibo_Kids/releases/download/v1.0.0/jibo_release_part_aa",
    ],
    "jibo_release_part_ab": [
        "https://github.com/balaji1312/Jibo_Kids/releases/download/v1.0.0/jibo_release_part_ab",
    ]
}

def download_with_resume(target_file: Path, urls: list[str], max_retries: int = 15) -> bool:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    
    for url in urls:
        print(f"Attempting download for {target_file.name} from {url}...")
        retries = 0
        
        while retries < max_retries:
            existing_size = target_file.stat().st_size if target_file.exists() else 0
            
            headers = {"User-Agent": "LUMI-Jibo-Downloader/1.0"}
            if existing_size > 0:
                headers["Range"] = f"bytes={existing_size}-"
            
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    total_expected = existing_size
                    content_length = resp.headers.get("Content-Length")
                    content_range = resp.headers.get("Content-Range")
                    
                    if content_length:
                        total_expected += int(content_length)
                    elif content_range and "/" in content_range:
                        total_expected = int(content_range.split("/")[-1])
                    
                    status = resp.status
                    print(f"[{target_file.name}] HTTP {status}. Resuming from {existing_size / (1024*1024):.1f} MB (Expected total: {total_expected / (1024*1024):.1f} MB)")
                    
                    mode = "ab" if (existing_size > 0 and status == 206) else "wb"
                    if mode == "wb":
                        existing_size = 0
                    
                    with open(target_file, mode) as f:
                        last_log = time.time()
                        downloaded = existing_size
                        
                        while True:
                            chunk = resp.read(1024 * 1024)  # 1MB chunk
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            now = time.time()
                            if now - last_log >= 5:
                                pct = (downloaded / total_expected * 100) if total_expected > 0 else 0
                                print(f"[{target_file.name}] {downloaded / (1024*1024):.1f} MB ({pct:.1f}%)")
                                last_log = now
                
                print(f"[{target_file.name}] Successfully downloaded ({target_file.stat().st_size / (1024*1024):.1f} MB)")
                return True
                
            except urllib.error.HTTPError as e:
                if e.code == 416:
                    print(f"[{target_file.name}] HTTP 416 Range Not Satisfiable (file likely complete: {existing_size / (1024*1024):.1f} MB)")
                    return True
                print(f"[{target_file.name}] HTTP error {e.code}: {e.reason}. Retrying in 5s...")
            except Exception as e:
                print(f"[{target_file.name}] Connection error: {e}. Retrying ({retries+1}/{max_retries})...")
            
            retries += 1
            time.sleep(min(2 ** retries, 30))
            
    return False

def combine_and_extract():
    part_aa = DATASET_DIR / "jibo_release_part_aa"
    part_ab = DATASET_DIR / "jibo_release_part_ab"
    combined_zip = DATASET_DIR / "combined.zip"
    data_dir = DATASET_DIR / "data"
    
    if data_dir.exists() and any(data_dir.iterdir()):
        print(f"Data directory already extracted at {data_dir}")
        return True

    print("Concatenating release parts into combined.zip...")
    with open(combined_zip, "wb") as out_f:
        with open(part_aa, "rb") as in_aa:
            while chunk := in_aa.read(16 * 1024 * 1024):
                out_f.write(chunk)
        with open(part_ab, "rb") as in_ab:
            while chunk := in_ab.read(16 * 1024 * 1024):
                out_f.write(chunk)
                
    print(f"combined.zip created ({combined_zip.stat().st_size / (1024*1024):.1f} MB). Extracting...")
    with zipfile.ZipFile(combined_zip, "r") as z:
        z.extractall(DATASET_DIR)
        
    print(f"Extraction complete! Data directory present at {data_dir}")
    return True

if __name__ == "__main__":
    for name, urls in URLS.items():
        file_path = DATASET_DIR / name
        success = download_with_resume(file_path, urls)
        if not success:
            print(f"Failed to download {name}", file=sys.stderr)
            sys.exit(1)
            
    combine_and_extract()
    print("ALL DONE!")

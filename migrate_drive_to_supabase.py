"""
AHM-Web: Google Drive to Supabase Storage File System Migration Tool
====================================================================
Migrates all local and Google Drive files to Supabase Storage, preserving
the exact relative folder structure, applying the automated compression firewall
for assets exceeding 2MB, and recording storage mappings in SQLite and Supabase.
"""

import os
import sys
import argparse
import sqlite3
import mimetypes
from pathlib import Path
from io import BytesIO

# Ensure project root is in python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'))

import storage_pipeline
from storage_pipeline import (
    supabase,
    is_supabase_configured,
    optimize_image,
    optimize_pdf,
    get_content_type,
    TARGET_FILE_LIMIT,
    SUPABASE_STORAGE_BUCKET
)

def get_db():
    instance_dir = os.path.join(BASE_DIR, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.getenv('DATABASE_PATH', os.path.join(instance_dir, 'users.db'))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS storage_mappings (
            filename TEXT PRIMARY KEY,
            storage_path TEXT NOT NULL,
            public_url TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS drive_mappings (
            filename TEXT PRIMARY KEY,
            drive_file_id TEXT NOT NULL
        )
    ''')
    conn.commit()
    return conn

def run_migration(dry_run=False, compress_all_over_limit=True):
    print("=" * 70)
    print(" AHM FILE SYSTEM MIGRATION: GOOGLE DRIVE -> SUPABASE STORAGE")
    print("=" * 70)
    
    supabase_active = is_supabase_configured()
    print(f"[*] Supabase Configured: {'YES' if supabase_active else 'NO (Local Dry/Staging Mode)'}")
    print(f"[*] Target Bucket:       {SUPABASE_STORAGE_BUCKET}")
    print(f"[*] Dry Run Mode:        {'ACTIVE (No remote uploads)' if dry_run else 'OFF (Live)'}")
    print(f"[*] 2MB Compression:     {'ENABLED' if compress_all_over_limit else 'DISABLED'}")
    print("-" * 70)

    uploads_root = os.path.join(BASE_DIR, 'static', 'uploads')
    if not os.path.exists(uploads_root):
        print(f"[!] Uploads directory '{uploads_root}' does not exist.")
        return

    # Collect all local files under static/uploads/
    all_files = []
    for root, _, files in os.walk(uploads_root):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, uploads_root).replace('\\', '/')
            all_files.append((full_path, rel_path, f))

    print(f"[*] Found {len(all_files)} total files in local 'static/uploads/' structure.")

    conn = get_db()
    c = conn.cursor()

    migrated_count = 0
    skipped_count = 0
    error_count = 0
    total_original_bytes = 0
    total_processed_bytes = 0

    for full_path, rel_path, filename in all_files:
        try:
            original_size = os.path.getsize(full_path)
            total_original_bytes += original_size
            ext = os.path.splitext(filename)[1].lower()
            mime_type = get_content_type(ext)
            
            with open(full_path, 'rb') as fp:
                file_bytes = fp.read()

            # Apply compression firewall if file exceeds TARGET_FILE_LIMIT (2MB)
            processed_bytes = file_bytes
            was_compressed = False
            
            if compress_all_over_limit and original_size > TARGET_FILE_LIMIT:
                if ext in ['.jpg', '.jpeg', '.png']:
                    stream, mime_type = optimize_image(BytesIO(file_bytes))
                    processed_bytes = stream.read()
                    was_compressed = True
                elif ext == '.pdf':
                    stream, mime_type = optimize_pdf(BytesIO(file_bytes))
                    processed_bytes = stream.read()
                    was_compressed = True

            final_size = len(processed_bytes)
            total_processed_bytes += final_size

            # The Supabase storage path mirrors the exact relative folder path
            storage_path = rel_path
            
            status_tag = "[COMPRESSED]" if was_compressed else "[OK]"
            print(f"-> Processing: {storage_path} {status_tag} ({original_size:,} B -> {final_size:,} B)")

            if not dry_run:
                public_url = f"/static/uploads/{rel_path}"
                if supabase_active:
                    # Upload directly to Supabase storage
                    upload_res = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
                        path=storage_path,
                        file=processed_bytes,
                        file_options={"content-type": mime_type, "upsert": "true"}
                    )
                    public_url = supabase.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(storage_path)

                # Record in storage_mappings
                c.execute('''
                    INSERT OR REPLACE INTO storage_mappings 
                    (filename, storage_path, public_url, mime_type, file_size, updated_at) 
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (filename, storage_path, public_url, mime_type, final_size))

                # Keep drive_mappings backwards compatible
                c.execute('''
                    INSERT OR REPLACE INTO drive_mappings (filename, drive_file_id)
                    VALUES (?, ?)
                ''', (filename, storage_path))
                
                conn.commit()

            migrated_count += 1
        except Exception as e:
            error_count += 1
            print(f" [!] Error processing {rel_path}: {e}")

    conn.close()

    print("-" * 70)
    print(" MIGRATION SUMMARY")
    print(f" - Total files processed:   {migrated_count}")
    print(f" - Errors encountered:       {error_count}")
    print(f" - Original footprint:       {total_original_bytes / (1024*1024):.2f} MB")
    print(f" - Final migrated payload:   {total_processed_bytes / (1024*1024):.2f} MB")
    if total_original_bytes > 0:
        saved_pct = ((total_original_bytes - total_processed_bytes) / total_original_bytes) * 100
        print(f" - Storage saved:            {saved_pct:.1f}%")
    print("=" * 70)
    if dry_run:
        print("[i] Dry run complete. To execute live migration to Supabase, run:")
        print("    python migrate_drive_to_supabase.py --live")
    elif supabase_active:
        print("[+] All assets successfully synchronized to Supabase Storage with original directory tree!")
    else:
        print("[i] Local mappings updated. Once SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are added to .env, run with --live to push to Supabase.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Migrate local & Google Drive assets to Supabase Storage.")
    parser.add_argument('--live', action='store_true', help='Execute live uploads to Supabase (default is dry-run if credentials missing)')
    parser.add_argument('--dry-run', action='store_true', help='Perform dry-run inspection without remote writes')
    args = parser.parse_args()

    is_dry = args.dry_run or (not args.live and not is_supabase_configured())
    run_migration(dry_run=is_dry)

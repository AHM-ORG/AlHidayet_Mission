import os
import sqlite3
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from pypdf import PdfWriter
except ImportError:
    PdfWriter = None

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None
from dotenv import load_dotenv

# Load environment configuration
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Supabase Credentials Configuration (Permanent Service Role Key ensures tokens never expire)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://supabase.co").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "your-permanent-service-role-key")).strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "documents").strip()

# Initialize Supabase Client using permanent backend service keys
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as _e:
    print(f" [SUPABASE INIT WARNING] Could not initialize Supabase Client: {_e}")
    supabase = None

TARGET_FILE_LIMIT = 2 * 1024 * 1024  # 2 MB Threshold (2 * 1024 * 1024 bytes)

def is_supabase_configured() -> bool:
    """Checks whether valid Supabase credentials have been supplied."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    if "supabase.co" == SUPABASE_URL.lower() or "https://supabase.co" == SUPABASE_URL.lower():
        return False
    if "your-permanent-service-role-key" in SUPABASE_KEY.lower():
        return False
    return supabase is not None

def optimize_image(file_stream, quality=80):
    """
    Compresses images and converts alpha channels to RGB for JPEG formatting.
    Handles transparency gracefully by compositing over a solid white background.
    """
    img = Image.open(file_stream)
    output = BytesIO()
    
    # Handle transparent alpha channels before converting to JPEG
    if img.mode in ("RGBA", "LA", "PA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
        img = background
    elif img.mode in ("P", "CMYK", "YCbCr"):
        img = img.convert("RGB")
        
    img.save(output, format="JPEG", quality=quality, optimize=True)
    output.seek(0)
    return output, "image/jpeg"

def optimize_pdf(file_stream):
    """
    Reduces PDF payload footprint via internal content stream deflation using zlib/deflate.
    """
    writer = PdfWriter(clone_from=file_stream)
    for page in writer.pages:
        page.compress_content_streams()
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output, "application/pdf"

def get_content_type(extension):
    """Maps typical desktop file formats to internet MIME configurations."""
    types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.txt': 'text/plain',
        '.csv': 'text/csv'
    }
    return types.get(extension.lower(), 'application/octet-stream')

def get_sqlite_fallback_conn():
    """Provides a local SQLite connection to instance/users.db for fallback caching."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    instance_dir = os.path.join(base_dir, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.getenv('DATABASE_PATH', os.path.join(instance_dir, 'users.db'))
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Create local fallback tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            file_name TEXT NOT NULL,
            file_url TEXT NOT NULL,
            storage_path TEXT,
            mime_type TEXT,
            file_size INTEGER,
            status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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
    conn.commit()
    return conn

def handle_user_submission(file_bytes, filename, user_id):
    """
    Evaluates sizes, executes targeted resource reduction blocks, pushes
    objects directly into storage, and initializes the state in the review queue.
    """
    file_size = len(file_bytes)
    ext = os.path.splitext(filename)[1].lower()
    content_type = get_content_type(ext)
    
    if file_size <= TARGET_FILE_LIMIT:
        # Bypasses calculations entirely if the size constraint is met initially (<= 2MB)
        processed_file_bytes = file_bytes
    else:
        # Exceeds 2MB: process conditionally based on format
        file_stream = BytesIO(file_bytes)
        if ext in ['.jpg', '.jpeg', '.png']:
            processed_stream, content_type = optimize_image(file_stream)
            processed_file_bytes = processed_stream.read()
            # If PNG was converted to JPEG, normalize filename if appropriate
            if ext == '.png':
                filename = os.path.splitext(filename)[0] + '.jpg'
        elif ext == '.pdf':
            processed_stream, content_type = optimize_pdf(file_stream)
            processed_file_bytes = processed_stream.read()
        else:
            # Office docs (.docx, .xlsx, etc.) pass through directly without binary alteration
            processed_file_bytes = file_bytes

    storage_path = f"submissions/{filename}"
    bucket = SUPABASE_STORAGE_BUCKET
    
    # 1. Primary path: Supabase Storage & Database
    if is_supabase_configured():
        try:
            # Upload clean byte assets to Supabase Storage Bucket
            supabase.storage.from_(bucket).upload(
                path=storage_path,
                file=processed_file_bytes,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            file_url = supabase.storage.from_(bucket).get_public_url(storage_path)
            
            # Track reference metadata directly within the database table
            db_data = {
                "user_id": str(user_id) if user_id is not None else "anonymous",
                "file_name": filename,
                "file_url": file_url,
                "status": "pending_review"
            }
            response = supabase.table("user_posts").insert(db_data).execute()
            
            # Mirror to local DB for resilience & local search
            try:
                lconn = get_sqlite_fallback_conn()
                lc = lconn.cursor()
                post_id = response.data[0].get('id') if response.data else None
                lc.execute(
                    "INSERT INTO user_posts (id, user_id, file_name, file_url, storage_path, mime_type, file_size, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review')",
                    (post_id, str(user_id), filename, file_url, storage_path, content_type, len(processed_file_bytes))
                )
                lconn.commit()
                lconn.close()
            except Exception:
                pass
                
            return {
                "success": True,
                "message": "Success! Awaiting system authorization.",
                "data": response.data,
                "file_url": file_url,
                "original_size": file_size,
                "processed_size": len(processed_file_bytes)
            }
        except Exception as e:
            print(f" [SUPABASE PIPELINE ERROR] Supabase submission failed: {e}. Falling back to local queue.")

    # 2. Resilient local fallback path (when Supabase credentials are pending or unreachable)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_dir = os.path.join(base_dir, 'static', 'uploads', 'submissions')
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)
    with open(local_path, 'wb') as f:
        f.write(processed_file_bytes)
        
    file_url = f"/static/uploads/submissions/{filename}"
    lconn = get_sqlite_fallback_conn()
    lc = lconn.cursor()
    lc.execute(
        "INSERT INTO user_posts (user_id, file_name, file_url, storage_path, mime_type, file_size, status) VALUES (?, ?, ?, ?, ?, ?, 'pending_review')",
        (str(user_id), filename, file_url, storage_path, content_type, len(processed_file_bytes))
    )
    post_id = lc.lastrowid
    lconn.commit()
    lconn.close()
    
    fallback_record = [{
        "id": post_id,
        "user_id": str(user_id),
        "file_name": filename,
        "file_url": file_url,
        "status": "pending_review"
    }]
    
    return {
        "success": True,
        "message": "Success! Awaiting system authorization.",
        "data": fallback_record,
        "file_url": file_url,
        "original_size": file_size,
        "processed_size": len(processed_file_bytes)
    }

def fetch_public_content():
    """Retrieves only documents officially authorized by the moderation panel."""
    if is_supabase_configured():
        try:
            public_posts = supabase.table("user_posts").select("*").eq("status", "published").order("created_at", desc=True).execute()
            if public_posts.data:
                return public_posts.data
        except Exception as e:
            print(f" [SUPABASE FETCH ERROR] {e}. Falling back to local data.")
            
    # Local fallback
    try:
        conn = get_sqlite_fallback_conn()
        rows = conn.cursor().execute("SELECT * FROM user_posts WHERE status = 'published' ORDER BY created_at DESC").fetchall()
        data = [dict(r) for r in rows]
        conn.close()
        return data
    except Exception as e:
        print(f" [LOCAL FETCH ERROR] {e}")
        return []

def fetch_admin_queue():
    """Retrieves records requiring verification checks before active deployment."""
    if is_supabase_configured():
        try:
            pending_posts = supabase.table("user_posts").select("*").eq("status", "pending_review").order("created_at", desc=True).execute()
            if pending_posts.data:
                return pending_posts.data
        except Exception as e:
            print(f" [SUPABASE QUEUE ERROR] {e}. Falling back to local queue.")
            
    # Local fallback
    try:
        conn = get_sqlite_fallback_conn()
        rows = conn.cursor().execute("SELECT * FROM user_posts WHERE status = 'pending_review' ORDER BY created_at DESC").fetchall()
        data = [dict(r) for r in rows]
        conn.close()
        return data
    except Exception as e:
        print(f" [LOCAL QUEUE ERROR] {e}")
        return []

def approve_post(post_id):
    """Updates status parameters dynamically to transition files onto public views."""
    result = None
    if is_supabase_configured():
        try:
            response = supabase.table("user_posts").update({"status": "published"}).eq("id", post_id).execute()
            result = response.data
        except Exception as e:
            print(f" [SUPABASE APPROVE ERROR] {e}")

    # Synchronize local DB
    try:
        conn = get_sqlite_fallback_conn()
        c = conn.cursor()
        c.execute("UPDATE user_posts SET status = 'published', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
        conn.commit()
        if not result:
            row = c.execute("SELECT * FROM user_posts WHERE id = ?", (post_id,)).fetchone()
            result = [dict(row)] if row else []
        conn.close()
    except Exception as e:
        print(f" [LOCAL APPROVE ERROR] {e}")
        
    return result

def reject_post(post_id):
    """Rejects a submission, removing it from public view and pending review queue."""
    result = None
    if is_supabase_configured():
        try:
            response = supabase.table("user_posts").update({"status": "rejected"}).eq("id", post_id).execute()
            result = response.data
        except Exception as e:
            print(f" [SUPABASE REJECT ERROR] {e}")

    # Synchronize local DB
    try:
        conn = get_sqlite_fallback_conn()
        c = conn.cursor()
        c.execute("UPDATE user_posts SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
        conn.commit()
        if not result:
            row = c.execute("SELECT * FROM user_posts WHERE id = ?", (post_id,)).fetchone()
            result = [dict(row)] if row else []
        conn.close()
    except Exception as e:
        print(f" [LOCAL REJECT ERROR] {e}")
        
    return result

def delete_post(post_id):
    """Deletes post record from database and cleans up object from Supabase storage."""
    # Find post record first
    storage_path = None
    try:
        conn = get_sqlite_fallback_conn()
        row = conn.cursor().execute("SELECT * FROM user_posts WHERE id = ?", (post_id,)).fetchone()
        if row and row['storage_path']:
            storage_path = row['storage_path']
        conn.close()
    except Exception:
        pass

    if is_supabase_configured():
        try:
            # Query storage path from Supabase if not found locally
            if not storage_path:
                res = supabase.table("user_posts").select("storage_path").eq("id", post_id).execute()
                if res.data and res.data[0].get('storage_path'):
                    storage_path = res.data[0]['storage_path']
            
            if storage_path:
                supabase.storage.from_(SUPABASE_STORAGE_BUCKET).remove([storage_path])
                
            supabase.table("user_posts").delete().eq("id", post_id).execute()
        except Exception as e:
            print(f" [SUPABASE DELETE ERROR] {e}")

    try:
        conn = get_sqlite_fallback_conn()
        conn.cursor().execute("DELETE FROM user_posts WHERE id = ?", (post_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return True

# Standalone Supabase Storage operations
def upload_file_to_supabase(file_bytes, storage_path, content_type=None, bucket=None):
    """Directly uploads a file payload to Supabase Storage and returns its public URL."""
    bucket_name = bucket or SUPABASE_STORAGE_BUCKET
    if not content_type:
        ext = os.path.splitext(storage_path)[1].lower()
        content_type = get_content_type(ext)
        
    if not is_supabase_configured():
        return None
        
    try:
        supabase.storage.from_(bucket_name).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        public_url = supabase.storage.from_(bucket_name).get_public_url(storage_path)
        return public_url
    except Exception as e:
        print(f" [SUPABASE DIRECT UPLOAD ERROR] Failed to upload {storage_path}: {e}")
        return None

def delete_file_from_supabase(storage_path, bucket=None):
    """Removes an asset from Supabase Storage."""
    bucket_name = bucket or SUPABASE_STORAGE_BUCKET
    if not is_supabase_configured():
        return False
    try:
        supabase.storage.from_(bucket_name).remove([storage_path])
        return True
    except Exception as e:
        print(f" [SUPABASE DIRECT DELETE ERROR] Failed to delete {storage_path}: {e}")
        return False

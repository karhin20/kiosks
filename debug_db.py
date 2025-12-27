
import sys
import os
from app.supabase_client import get_supabase_client
from app.config import get_settings

def log(msg):
    print(msg)
    with open("debug_log.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def test_connection():
    try:
        # Clear previous log
        with open("debug_log.txt", "w", encoding="utf-8") as f:
            f.write("Starting debug...\n")

        settings = get_settings()
        log(f"URL configured: {bool(settings.SUPABASE_URL)}")
        log(f"Key configured: {bool(settings.SUPABASE_SERVICE_ROLE_KEY)}")
        
        log("Initializing Supabase client...")
        supabase = get_supabase_client()
        
        log("Querying products table...")
        # Add a timeout if possible? postgrest-py doesn't easily expose it via this client wrapper maybe.
        response = supabase.table("products").select("*").limit(5).execute()
        
        log(f"Success! Found {len(response.data)} products.")
        log(f"Data: {response.data}")
        
    except Exception as e:
        log(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    test_connection()

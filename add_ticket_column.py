
from database_manager import DatabaseManager
import streamlit as st

def add_column():
    print("Adding 'related_type' column to tickets table...")
    db = DatabaseManager()
    
    # Cloud
    if db.mode == "CLOUD":
        conn = db._get_cloud_conn()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE tickets ADD COLUMN related_type VARCHAR(50) DEFAULT 'asset'")
                conn.commit()
                print("✅ Column added in Cloud.")
            except Exception as e:
                print(f"Cloud: {e}")
            conn.close()
    
    # Local
    conn_local = db._get_local_conn()
    cursor_local = conn_local.cursor()
    try:
        cursor_local.execute("ALTER TABLE tickets ADD COLUMN related_type TEXT DEFAULT 'asset'")
        conn_local.commit()
        print("✅ Column added locally.")
    except Exception as e:
        print(f"Local: {e}")
    conn_local.close()

if __name__ == "__main__":
    add_column()

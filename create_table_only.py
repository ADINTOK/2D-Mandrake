
from database_manager import DatabaseManager
import mysql.connector
import streamlit as st

def create_table():
    print("Creating table kpu_enterprise_software...")
    db = DatabaseManager()
    
    # Cloud
    if db.mode == "CLOUD":
        conn = db._get_cloud_conn()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS kpu_enterprise_software (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(255),
                name VARCHAR(255),
                manufacturer VARCHAR(255),
                mfa_enabled VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;
            """)
            conn.commit()
            print("✅ Table created in Cloud.")
            conn.close()
    
    # Local
    conn_local = db._get_local_conn()
    cursor_local = conn_local.cursor()
    cursor_local.execute("""
    CREATE TABLE IF NOT EXISTS kpu_enterprise_software (
         id INTEGER PRIMARY KEY,
         asset_id TEXT,
         name TEXT,
         manufacturer TEXT,
         mfa_enabled TEXT,
         created_at TIMESTAMP
    )
    """)
    conn_local.commit()
    print("✅ Table created locally.")
    conn_local.close()

if __name__ == "__main__":
    create_table()

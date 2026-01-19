
from database_manager import DatabaseManager

def create_machine_table():
    print("Creating table kpu_enterprise_computing_machines...")
    db = DatabaseManager()
    
    # Cloud
    if db.mode == "CLOUD":
        conn = db._get_cloud_conn()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(255),
                name VARCHAR(255),
                ip_address VARCHAR(50),
                mac_address VARCHAR(50),
                owner VARCHAR(255),
                os_type VARCHAR(100),
                location VARCHAR(255),
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
    CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (
         id INTEGER PRIMARY KEY,
         asset_id TEXT,
         name TEXT,
         ip_address TEXT,
         mac_address TEXT,
         owner TEXT,
         os_type TEXT,
         location TEXT,
         created_at TIMESTAMP
    )
    """)
    conn_local.commit()
    print("✅ Table created locally.")
    conn_local.close()

if __name__ == "__main__":
    create_machine_table()

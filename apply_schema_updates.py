import mysql.connector
import sqlite3
import streamlit as st
import os

# =============================================================================
# Schema Sync Script
# =============================================================================
# Ensures that the V2 ITIL Tables exist in BOTH:
# 1. Cloud Database (MySQL)
# 2. Local Database (SQLite)
# =============================================================================

LOCAL_DB_FILE = "local_data.db"

def get_mysql_conn():
    if "mysql" in st.secrets:
        s = st.secrets["mysql"]
        return mysql.connector.connect(
            host=s["host"],
            user=s["user"],
            password=s["password"],
            database=s["database"],
            port=s.get("port", 3306)
        )
    return None

def get_sqlite_conn():
    return sqlite3.connect(LOCAL_DB_FILE)

def run_ddl(cursor, db_type):
    print(f"Applying Schema to {db_type}...")
    
    # 1. Knowledge Base
    if db_type == "mysql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_articles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            content TEXT,
            category VARCHAR(100),
            tags VARCHAR(255),
            author VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            category TEXT,
            tags TEXT,
            author TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # 2. SLA Policies
    if db_type == "mysql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sla_policies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            priority VARCHAR(50) UNIQUE,
            response_time_minutes INT,
            resolution_time_minutes INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sla_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            priority TEXT UNIQUE,
            response_time_minutes INTEGER,
            resolution_time_minutes INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
    
    # Seed SLAs if empty
    # SQLite/MySQL syntax for check is slightly diff but SELECT COUNT(*) works
    cursor.execute("SELECT COUNT(*) FROM sla_policies")
    count = cursor.fetchone()[0]
    if count == 0:
        print(f"  - Seeding SLAs in {db_type}...")
        slas = [
            ("Critical", 15, 60),
            ("High", 60, 240),
            ("Medium", 240, 1440),
            ("Low", 1440, 4320)
        ]
        if db_type == "mysql":
            cursor.executemany("INSERT INTO sla_policies (priority, response_time_minutes, resolution_time_minutes) VALUES (%s, %s, %s)", slas)
        else:
            cursor.executemany("INSERT INTO sla_policies (priority, response_time_minutes, resolution_time_minutes) VALUES (?, ?, ?)", slas)

    # 3. Problems
    if db_type == "mysql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            root_cause_analysis TEXT,
            status VARCHAR(50) DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            root_cause_analysis TEXT,
            status TEXT DEFAULT 'Open',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # 4. Software Licenses
    if db_type == "mysql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS software_licenses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            software_asset_id INT NOT NULL,
            license_key VARCHAR(255),
            vendor VARCHAR(255),
            total_seats INT DEFAULT 0,
            used_seats INT DEFAULT 0,
            expiration_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS software_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            software_asset_id INTEGER NOT NULL,
            license_key TEXT,
            vendor TEXT,
            total_seats INTEGER DEFAULT 0,
            used_seats INTEGER DEFAULT 0,
            expiration_date DATE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # 5. Change Approvals
    if db_type == "mysql":
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_approvals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticket_id INT NOT NULL,
            approver_role VARCHAR(100),
            status VARCHAR(50) DEFAULT 'Pending',
            comments TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_approvals_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """)
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            approver_role TEXT,
            status TEXT DEFAULT 'Pending',
            comments TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        )
        """)

    # 6. Alter Tickets (Columns)
    print(f"  - Checking 'tickets' columns in {db_type}...")
    # Add due_date
    try:
        if db_type == "mysql":
            cursor.execute("ALTER TABLE tickets ADD COLUMN due_date DATETIME")
        else:
            cursor.execute("ALTER TABLE tickets ADD COLUMN due_date DATETIME")
        print("    + Added 'due_date'")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "exists" in str(e).lower():
            pass
        else:
            print(f"    ! Note on due_date: {e}")

    # Add problem_id
    try:
        if db_type == "mysql":
            cursor.execute("ALTER TABLE tickets ADD COLUMN problem_id INT")
            try:
                cursor.execute("ALTER TABLE tickets ADD CONSTRAINT fk_ticket_problem FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE SET NULL")
            except: pass
        else:
            cursor.execute("ALTER TABLE tickets ADD COLUMN problem_id INTEGER REFERENCES problems(id) ON DELETE SET NULL")
        print("    + Added 'problem_id'")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "exists" in str(e).lower():
            pass
        else:
            print(f"    ! Note on problem_id: {e}")
            
    # Add status (Already exists typically, but ensuring for completeness if needed? No, user didn't ask for that, status exists)


def sync_all():
    # 1. Cloud
    try:
        mysql_conn = get_mysql_conn()
        if mysql_conn:
            run_ddl(mysql_conn.cursor(), "mysql")
            mysql_conn.commit()
            mysql_conn.close()
        else:
            print("Skipping Cloud (No secrets configured)")
    except Exception as e:
        print(f"Cloud Sync Failed: {e}")

    # 2. Local
    try:
        sqlite_conn = get_sqlite_conn()
        run_ddl(sqlite_conn.cursor(), "sqlite")
        sqlite_conn.commit()
        sqlite_conn.close()
    except Exception as e:
        print(f"Local Sync Failed: {e}")

if __name__ == "__main__":
    sync_all()
    print("Done.")

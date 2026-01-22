import sqlite3
import mysql.connector
import streamlit as st
import os
import re
import time
import socket
from datetime import datetime, timedelta
import json
import shutil
# Fixed import path after move to utils
from utils.sshtunnel_helper import SSHTunnel

try:
    from passlib.hash import pbkdf2_sha256
except ImportError:
    pbkdf2_sha256 = None

# =============================================================================
# Database Manager
# =============================================================================
# This class acts as a crucial abstraction layer between the Streamlit UI and
# the underlying data storage.
#
# Core Responsibilities:
# 1. Hybrid Connectivity: Checks for Cloud MySQL; falls back to Local SQLite.
# 2. Query Translation: Converts MySQL syntax (e.g., %s) to SQLite (?) on the fly.
# 3. Data Synchronization: Pulls fresh data from Cloud to Local cache.
# 4. SSH Tunneling: Securely connects to VPS databases via SSH Port Forwarding.
# =============================================================================

class DatabaseManager:
    """
    Manages hybrid database connections (Cloud MySQL + Local SQLite).
    """
    VERSION_ID = "2.1.V01" # Incremented to force session state reset
    
    def __init__(self, secrets_override=None):
        """
        Initializes the manager, tests cloud connection, and sets initial mode.
        Does NOT trigger a full sync automatically to prevent blocking; calls sync() if connected.
        """
        self.secrets_override = secrets_override
        self.mode = "PENDING" # "CLOUD" or "LOCAL"
        self.cloud_source = None # "PRIMARY" or "BACKUP"
        self.local_db = "local_cache.db"
        self.status_msg = "Initializing..."
        self.ssh_tunnel = None # Helper instance
        self.ssh_local_port = None
        
        # Aggressive Secrets Loading (Bypass stale st.secrets)
        if not self.secrets_override:
            try:
                import toml
                path = ".streamlit/secrets.toml"
                if os.path.exists(path):
                    self.secrets_override = toml.load(path)
            except:
                pass
        
        # Try Cloud First
        self.last_error = None
        if self._test_cloud_connection():
            self.mode = "CLOUD"
            src_label = "Primary" if self.cloud_source == "PRIMARY" else "Secondary (Backup)"
            
            if self.ssh_tunnel:
                src_label += " via SSH"
                
            self.status_msg = f"🟢 Cloud Connected ({src_label})"
            # Attempt Sync logic moved to explicit method to avoid long startup hangs on slow connections
            self.sync()
        else:
            self.mode = "LOCAL"
            if not self.last_error:
                self.status_msg = f"🟠 Offline Mode (No Clouds Configured) [v{self.VERSION_ID}]"
            else:
                self.status_msg = f"🟠 Offline Mode ({self.last_error}) [v{self.VERSION_ID}]"
            self._ensure_local_schema()

    def sync(self):
        """
        Public sync method to trigger Cloud -> Local synchronization.
        
        Returns:
            tuple: (success (bool), message (str))
        """
        print("Starting Sync...")
        if self.mode == "CLOUD":
            try:
                self._sync_schema()
                self._sync_data()
                src_label = "Primary" if self.cloud_source == "PRIMARY" else "Secondary"
                if self.ssh_tunnel: src_label += " (SSH)"
                
                self.status_msg = f"🟢 Cloud Connected ({src_label} - Synced)"
                print("Sync Complete")
                return True, "Sync Successful"
            except Exception as e:
                print(f"Sync Warning: {e}")
                self.status_msg = "🟢 Cloud Connected (Sync Failed)"
                return False, str(e)
        else:
            # Try to reconnect
            if self._test_cloud_connection():
                self.mode = "CLOUD"
                return self.sync()
            else:
                return False, "Cannot Sync: Cloud Unreachable"

    def _test_cloud_connection(self):
        """
        Probes the cloud database to check reachability.
        
        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            conn = self._get_cloud_conn()
            if conn and conn.is_connected():
                conn.close()
                return True
            else:
                self.last_error = "Connection Failed"
        except Exception as e:
            self.last_error = str(e)
            return False
        return False

    def _get_cloud_conn(self):
        """
        Establishes a connection to Cloud MySQL. Implement Failover.
        Priority: 1. [mysql] (Primary) -> 2. [mysql_backup] (Backup)
        """
        active_secrets = self.secrets_override if self.secrets_override else st.secrets

        # 1. Try Primary
        if "mysql" in active_secrets:
            try:
                conn = self._connect_to_source(active_secrets["mysql"])
                if conn and conn.is_connected():
                    self.cloud_source = "PRIMARY"
                    print("Connected to Primary Cloud Node")
                    return conn
            except Exception as e:
                print(f"Primary Cloud Connection Attempt Failed: {e}")

        # 2. Try Backup
        if "mysql_backup" in active_secrets:
            try:
                conn = self._connect_to_source(active_secrets["mysql_backup"])
                if conn and conn.is_connected():
                    self.cloud_source = "BACKUP"
                    print("Connected to Backup Cloud Node")
                    return conn
            except Exception as e:
                print(f"Backup Cloud Connection Attempt Failed: {e}")

        return None

    def ensure_cloud_schema(self, target="PRIMARY"):
        """
        Creates missing system tables in the Cloud Database (Platform repair).
        Uses MySQL DDL.
        """
        config = st.secrets["mysql"] if target == "PRIMARY" else st.secrets["mysql_backup"]
        try:
            conn = self._connect_to_source(config)
            cur = conn.cursor()
            
            # --- DDL Definitions (MySQL Compatible) ---
            # Using IF NOT EXISTS
            
            # 1. Assets
            cur.execute("""CREATE TABLE IF NOT EXISTS assets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                parent_id INT,
                type VARCHAR(50),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )""")
            
            # 2. Tickets (Includes new columns)
            cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id INT,
                related_type VARCHAR(50),
                ticket_type VARCHAR(50),
                title VARCHAR(255),
                description TEXT,
                status VARCHAR(50),
                priority VARCHAR(50),
                logged_by VARCHAR(100),
                assigned_to VARCHAR(100),
                due_date TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )""")

            # 3. Ticket Assets (Join Table)
            cur.execute("""CREATE TABLE IF NOT EXISTS ticket_assets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticket_id INT,
                asset_id INT,
                asset_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_ticket (ticket_id)
            )""")
            
            # 4. Attachments
            cur.execute("""CREATE TABLE IF NOT EXISTS ticket_attachments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticket_id INT,
                file_name VARCHAR(255),
                file_path TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_ticket_att (ticket_id)
            )""")
            
            # 5. Core KPU Tables (Hierarchy)
            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_business_services_level1 (
                 id INT AUTO_INCREMENT PRIMARY KEY,
                 name VARCHAR(255), 
                 description TEXT, 
                 owner VARCHAR(100), 
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_business_services_level2 (
                 id INT AUTO_INCREMENT PRIMARY KEY,
                 business_service_level1_id INT,
                 name VARCHAR(255), 
                 description TEXT, 
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_technical_services (
                 id INT AUTO_INCREMENT PRIMARY KEY,
                 business_service_level2_id INT, 
                 name VARCHAR(255), 
                 description TEXT, 
                 sla_level VARCHAR(50), 
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_assets (
                 id INT AUTO_INCREMENT PRIMARY KEY,
                 technical_service_id INT, 
                 name VARCHAR(255), 
                 asset_type VARCHAR(50), 
                 location VARCHAR(100), 
                 status VARCHAR(50), 
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_component_assets (
                 id INT AUTO_INCREMENT PRIMARY KEY,
                 enterprise_asset_id INT, 
                 name VARCHAR(255), 
                 component_type VARCHAR(50), 
                 version VARCHAR(50), 
                 description TEXT, 
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_software (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(50),
                name VARCHAR(255),
                manufacturer VARCHAR(100),
                mfa_enabled VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id VARCHAR(50),
                name VARCHAR(255),
                ip_address VARCHAR(50),
                mac_address VARCHAR(50),
                owner VARCHAR(100),
                os_type VARCHAR(50),
                location VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS software_licenses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                software_asset_id INT,
                license_key VARCHAR(255),
                vendor VARCHAR(255),
                total_seats INT DEFAULT 1,
                used_seats INT DEFAULT 0,
                expiration_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            # 6. Compliance / Controls
            cur.execute("""CREATE TABLE IF NOT EXISTS problems (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255),
                description TEXT,
                root_cause_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS iso_controls (
                id VARCHAR(50) PRIMARY KEY,
                description TEXT,
                category VARCHAR(100),
                theme VARCHAR(100)
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS nist_controls (
                id VARCHAR(50) PRIMARY KEY,
                function VARCHAR(100),
                category VARCHAR(100),
                subcategory VARCHAR(100),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS policies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                category VARCHAR(100),
                summary TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS sla_policies (
                priority VARCHAR(50) PRIMARY KEY,
                response_time_minutes INT,
                resolution_time_minutes INT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )""")

            # 7. Mappings
            cur.execute("""CREATE TABLE IF NOT EXISTS asset_controls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id INT,
                control_id VARCHAR(50),
                related_type VARCHAR(50),
                status VARCHAR(50),
                notes TEXT,
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS asset_nist_controls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                asset_id INT,
                control_id VARCHAR(50),
                related_type VARCHAR(50),
                status VARCHAR(50),
                notes TEXT,
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            cur.execute("""CREATE TABLE IF NOT EXISTS policy_nist_mappings (
                policy_id INT,
                nist_control_id VARCHAR(50),
                PRIMARY KEY (policy_id, nist_control_id)
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS companion_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password_hash VARCHAR(255),
                full_name VARCHAR(255),
                email VARCHAR(255),
                role VARCHAR(50) DEFAULT 'user',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

            # Auto-Migration: Add is_active
            try:
                cur.execute("SELECT is_active FROM companion_users LIMIT 1")
                cur.fetchall()
            except:
                try:
                    cur.execute("ALTER TABLE companion_users ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
                except: pass

            # Auto-Migration: Add role
            try:
                cur.execute("SELECT role FROM companion_users LIMIT 1")
                cur.fetchall()
            except:
                try:
                    cur.execute("ALTER TABLE companion_users ADD COLUMN role VARCHAR(50) DEFAULT 'user'")
                except: pass

            # Auto-Migration: Add full_name
            try:
                cur.execute("SELECT full_name FROM companion_users LIMIT 1")
                cur.fetchall()
            except:
                try:
                    cur.execute("ALTER TABLE companion_users ADD COLUMN full_name VARCHAR(255)")
                except: pass

            cur.execute("""CREATE TABLE IF NOT EXISTS ticket_comments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticket_id INT,
                author VARCHAR(100),
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_ticket_comments (ticket_id)
            )""")

            conn.commit()
            conn.close()
            return True, "Schema Repair Complete."
            
        except Exception as e:
            return False, str(e)

        # 1. Try Primary
        if 'mysql' in active_secrets:
            try:
                conn = connect_with_ssh_check(active_secrets["mysql"])
                if conn.is_connected():
                    self.cloud_source = "PRIMARY"
                    return conn
            except Exception as e:
                print(f"Primary DB Connect Failed: {e}")
        
        # 2. Try Backup
        if 'mysql_backup' in active_secrets:
            print("Attempting Backup DB Connection...")
            try:
                conn = connect_with_ssh_check(active_secrets["mysql_backup"])
                if conn.is_connected():
                    self.cloud_source = "BACKUP"
                    print("✅ Connected to Backup DB")
                    return conn
            except Exception as e:
                print(f"Backup DB Connect Failed: {e}")
                
        return None

    def _get_vps_conn(self):
        """
        Specifically establishes a connection to the Linux VPS (dubaytech_db).
        Used for Companion User management which is centralized on the VPS.
        """
        active_secrets = self.secrets_override if self.secrets_override else st.secrets
        vps_ip = "74.208.225.182"
        
        # Find which config is the VPS
        vps_cfg = None
        if 'mysql' in active_secrets and active_secrets['mysql'].get('host') == vps_ip:
            vps_cfg = active_secrets['mysql']
        elif 'mysql_backup' in active_secrets and active_secrets['mysql_backup'].get('host') == vps_ip:
            vps_cfg = active_secrets['mysql_backup']
            
        if not vps_cfg:
            print("ERROR: VPS Configuration not found in secrets.")
            return None

        # Reuse existing SSH tunnel if already open to the VPS IP
        db_host = vps_cfg['host']
        db_port = vps_cfg.get("port", 3306)

        if 'ssh' in active_secrets and active_secrets['ssh'].get('host') == vps_ip:
            if not self.ssh_tunnel:
                 # Logic copied from _get_cloud_conn for simplicity, or we could refactor
                 print(f"Opening SSH Tunnel to VPS {db_host} for User Management...")
                 ssh_cfg = active_secrets['ssh']
                 from utils.sshtunnel_helper import SSHTunnel
                 try:
                     self.ssh_tunnel = SSHTunnel(
                         ssh_host=ssh_cfg['host'],
                         ssh_user=ssh_cfg['user'],
                         ssh_password=ssh_cfg['password'],
                         remote_bind_address=('127.0.0.1', 3306),
                         ssh_port=ssh_cfg.get('port', 22)
                     )
                     self.ssh_local_port = self.ssh_tunnel.start()
                 except Exception as e:
                     print(f"SSH Tunnel for VPS failed: {e}")
                     return None
            
            db_host = '127.0.0.1'
            db_port = self.ssh_local_port

        try:
            return mysql.connector.connect(
                host=db_host,
                user=vps_cfg['user'],
                password=vps_cfg['password'],
                database=vps_cfg['database'],
                port=db_port,
                connection_timeout=10
            )
        except Exception as e:
            print(f"VPS Connection Error: {e}")
            return None

    def _get_local_conn(self):
        """
        Establishes a connection to the Local SQLite cache.
        
        Returns:
            sqlite3.Connection: Connection object.
        """
        return sqlite3.connect(self.local_db, check_same_thread=False)

    def execute(self, query, params=None, fetch=False):
        """
        Unified executor for running queries against the active database (Cloud or Local).
        Handles SQL dialect translation (MySQL -> SQLite) automatically when in LOCAL mode.
        
        Args:
            query (str): SQL query (MySQL syntax).
            params (tuple, optional): Parameters for the query.
            fetch (bool): If True, returns fetched results.
            
        Returns:
            list/bool: Result list if fetch=True, else success boolean.
        """
        
        # 1. CLOUD MODE
        if self.mode == "CLOUD":
            try:
                conn = self._get_cloud_conn()
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params or ())
                if fetch:
                    res = cursor.fetchall()
                    conn.close()
                    return res
                else:
                    conn.commit()
                    conn.close()
                    return True
            except Exception as e:
                # Auto-Fallback logic? 
                # For now, just error, or we could switch mode dynamically.
                # Let's switch mode if connection completely fails
                print(f"Cloud Error: {e}. Switching to Local.")
                self.mode = "LOCAL"
                self.status_msg = f"🟠 Offline Mode ({str(e)}) [Fallback]"
                return self.execute(query, params, fetch)

        # 2. LOCAL MODE
        if self.mode == "LOCAL":
            # Convert MySQL query to SQLite
            # 1. Replace %s with ?
            sqlite_query = query.replace("%s", "?")
            # 2. Handle NOW() -> datetime('now')
            sqlite_query = sqlite_query.replace("NOW()", "datetime('now')")
            # 3. Handle INSERT IGNORE -> INSERT OR IGNORE
            sqlite_query = sqlite_query.replace("INSERT IGNORE", "INSERT OR IGNORE")
            # 4. Handle ON DUPLICATE KEY UPDATE (Complex)
            # SQLite uses ON CONFLICT DO UPDATE.
            # Simplified approach: for simple upserts, it might fail or we rely on replace.
            # For this app, the critical UPSERTs are in Link functions.
            if "ON DUPLICATE KEY UPDATE" in sqlite_query:
                # Crude Rewrite for specific known queries
                if "asset_controls" in sqlite_query or "asset_nist_controls" in sqlite_query:
                    # Convert to INSERT OR REPLACE
                    sqlite_query = re.sub(r"INSERT INTO", "INSERT OR REPLACE INTO", sqlite_query, flags=re.IGNORECASE)
                    sqlite_query = sqlite_query.split("ON DUPLICATE")[0] # Strip the update part method

            conn = self._get_local_conn()
            # Row factory for dictionary-like access
            conn.row_factory = self._dict_factory
            cursor = conn.cursor()
            try:
                cursor.execute(sqlite_query, params or ())
                if fetch:
                    res = cursor.fetchall()
                    conn.close()
                    return res
                else:
                    conn.commit()
                    conn.close()
                    return True
            except Exception as e:
                st.error(f"Local DB Error: {e}")
                conn.close()
                return [] if fetch else False

    def _dict_factory(self, cursor, row):
        """Helper to convert SQLite tuples to dictionaries."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    # --- SYNC LOGIC ---
    def _ensure_local_schema(self):
        """Creates SQLite tables if missing."""
        conn = self._get_local_conn()
        cur = conn.cursor()
        
        # Assets
        cur.execute("""CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY,
            name TEXT,
            parent_id INTEGER,
            type TEXT,
            description TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )""")
        
        # Tickets
        cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER,
            related_type TEXT,
            ticket_type TEXT,
            title TEXT,
            description TEXT,
            status TEXT,
            priority TEXT,
            logged_by TEXT,
            assigned_to TEXT,
            due_date TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )""")
        
        # Migration: Ensure new columns exist (SQLite doesn't support IF NOT EXISTS in ADD COLUMN standardly well in all versions, simple try/except is best)
        try:
            cur.execute("ALTER TABLE tickets ADD COLUMN due_date TIMESTAMP")
        except: pass
        
        try:
            cur.execute("ALTER TABLE tickets ADD COLUMN assigned_to TEXT")
        except: pass

        # Attachments
        cur.execute("""CREATE TABLE IF NOT EXISTS ticket_attachments (
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            uploaded_at TIMESTAMP
        )""")
        
        # ISO Controls
        cur.execute("""CREATE TABLE IF NOT EXISTS iso_controls (
            id TEXT PRIMARY KEY,
            description TEXT,
            category TEXT,
            theme TEXT
        )""")
        
        # NIST Controls
        cur.execute("""CREATE TABLE IF NOT EXISTS nist_controls (
            id TEXT PRIMARY KEY,
            function TEXT,
            category TEXT,
            subcategory TEXT,
            description TEXT,
            created_at TIMESTAMP
        )""")
        
        # Policies
        cur.execute("""CREATE TABLE IF NOT EXISTS policies (
            id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            summary TEXT,
            content TEXT,
            created_at TIMESTAMP
        )""")
        
        # Mappings
        cur.execute("""CREATE TABLE IF NOT EXISTS asset_controls (
            asset_id INTEGER,
            control_id TEXT,
            status TEXT,
            notes TEXT,
            linked_at TIMESTAMP,
            PRIMARY KEY (asset_id, control_id)
        )""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS asset_nist_controls (
            asset_id INTEGER,
            control_id TEXT,
            status TEXT,
            notes TEXT,
            linked_at TIMESTAMP,
            PRIMARY KEY (asset_id, control_id)
        )""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS policy_nist_mappings (
            policy_id INTEGER,
            nist_control_id TEXT,
            PRIMARY KEY (policy_id, nist_control_id)
        )""")

        # --- Hierarchy v2.0 Local Tables ---
        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_business_services_level1 (
             id INTEGER PRIMARY KEY,
             name TEXT, 
             description TEXT, 
             owner TEXT, 
             created_at TIMESTAMP
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_business_services_level2 (
             id INTEGER PRIMARY KEY,
             business_service_level1_id INTEGER,
             name TEXT, 
             description TEXT, 
             created_at TIMESTAMP
        )""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_technical_services (
             id INTEGER PRIMARY KEY,
             business_service_level2_id INTEGER, 
             name TEXT, 
             description TEXT, 
             sla_level TEXT, 
             created_at TIMESTAMP
        )""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_assets (
             id INTEGER PRIMARY KEY,
             technical_service_id INTEGER, 
             name TEXT, 
             asset_type TEXT, 
             location TEXT, 
             status TEXT, 
             created_at TIMESTAMP
        )""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_component_assets (
             id INTEGER PRIMARY KEY,
             enterprise_asset_id INTEGER, 
             name TEXT, 
             component_type TEXT, 
             version TEXT, 
             description TEXT, 
             created_at TIMESTAMP
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_software (
            id INTEGER PRIMARY KEY,
            asset_id TEXT,
            name TEXT,
            manufacturer TEXT,
            mfa_enabled TEXT,
            created_at TIMESTAMP
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (
            id INTEGER PRIMARY KEY,
            asset_id TEXT,
            name TEXT,
            ip_address TEXT,
            mac_address TEXT,
            owner TEXT,
            os_type TEXT,
            location TEXT,
            created_at TIMESTAMP
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS software_licenses (
            id INTEGER PRIMARY KEY,
            software_asset_id INTEGER,
            license_key TEXT,
            vendor TEXT,
            total_seats INTEGER,
            used_seats INTEGER,
            expiration_date DATE,
            created_at TIMESTAMP
        )""")

        conn.commit()
        conn.close()

    def _sync_schema(self):
        # We assume _ensure_local_schema is 'close enough' for now.
        # True schema reflection is complex.
        self._ensure_local_schema()

    def _sync_data(self):
        """Pull data from Cloud and Push to Local"""
        
        # 0. PUSH Local Changes FIRST (Tickets only for now)
        try:
            self._push_local_tickets()
        except Exception as e:
            print(f"Push Sync Failed: {e}")
            
        # 0.5 SYNC Files (Local <-> Network)
        try:
            self._sync_files()
        except Exception as e:
            print(f"File Sync Failed: {e}")

        # We manually fetch tables and insert/replace
        tables = ['assets', 'tickets', 'iso_controls', 'nist_controls', 'policies', 
                  'asset_controls', 'asset_nist_controls', 'policy_nist_mappings', 'ticket_attachments',
                  'kpu_business_services_level1', 'kpu_business_services_level2', 'kpu_technical_services', 'kpu_enterprise_assets', 'kpu_component_assets', 'kpu_enterprise_software', 'kpu_enterprise_computing_machines']
        
        cloud_conn = self._get_cloud_conn()
        local_conn = self._get_local_conn()
        
        cursor_cloud = cloud_conn.cursor(dictionary=True)
        cursor_local = local_conn.cursor()
        
        for tbl in tables:
            try:
                # 1. Fetch Cloud
                cursor_cloud.execute(f"SELECT * FROM {tbl}")
                rows = cursor_cloud.fetchall()
                
                if not rows: continue
                
                # 2. Prep Local
                # Get columns from first row
                cols = list(rows[0].keys())
                placeholders = ",".join(["?"] * len(cols))
                col_names = ",".join(cols)
                
                sql = f"INSERT OR REPLACE INTO {tbl} ({col_names}) VALUES ({placeholders})"
                
                # 3. Bulk Insert
                data = []
                for r in rows:
                    data.append(tuple(r.values()))
                    
                cursor_local.executemany(sql, data)
                
            except Exception as e:
                print(f"Sync error on {tbl}: {e}")
                
        local_conn.commit()
        local_conn.close()
        cloud_conn.close()

    def _push_local_tickets(self):
        """
        Identifies locally created tickets (offline) and pushes them to Cloud.
        Strategy: Check for tickets in Local that don't match (Title + Date + User) in Cloud.
        """
        print("Pushing Local Tickets to Cloud...")
        local_conn = self._get_local_conn()
        local_conn.row_factory = self._dict_factory
        cur_local = local_conn.cursor()
        
        cloud_conn = self._get_cloud_conn()
        cur_cloud = cloud_conn.cursor(dictionary=True)
        
        # Get all local tickets
        cur_local.execute("SELECT * FROM tickets")
        local_tickets = cur_local.fetchall()
        
        pushed_count = 0
        
        for t in local_tickets:
            # Check if exists in Cloud (Composite Key: Title, LoggedBy, CreatedAt approx)
            # Timestamps might drift slightly between SQL types, so we check title + user + asset
            check_sql = "SELECT id FROM tickets WHERE title=%s AND logged_by=%s AND asset_id=%s"
            cur_cloud.execute(check_sql, (t['title'], t['logged_by'], t['asset_id']))
            exists = cur_cloud.fetchone()
            
            if not exists:
                print(f"Syncing Ticket: {t['title']}")
                # Insert into Cloud
                ins_sql = """INSERT INTO tickets (asset_id, ticket_type, title, description, priority, status, logged_by, created_at, updated_at) 
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                cur_cloud.execute(ins_sql, (t['asset_id'], t['ticket_type'], t['title'], t['description'], 
                                            t['priority'], t['status'], t['logged_by'], t['created_at'], t['updated_at']))
                
                # Get new Cloud ID
                new_id = cur_cloud.lastrowid
                
                # Update Local Record to match Cloud ID (Reconciliation)
                # This prevents duplicate creates on next sync
                # Also we must update attachments to point to new ID
                old_id = t['id']
                cur_local.execute("UPDATE tickets SET id = ? WHERE id = ?", (new_id, old_id))
                cur_local.execute("UPDATE ticket_attachments SET ticket_id = ? WHERE ticket_id = ?", (new_id, old_id))
                
                pushed_count += 1
                
        if pushed_count > 0:
            print(f"Pushed {pushed_count} tickets to Cloud.")
            cloud_conn.commit()
            local_conn.commit()
            
        cur_cloud.close()
        cloud_conn.close()
        cur_local.close()
        cur_local.close()
        local_conn.close()

    def get_storage_config(self):
        """
        Retrieves storage configuration from 'app_config.json'.
        
        Returns:
            dict: A dictionary containing 'local_path' and 'network_path'.
                  Defaults to '2D_Storage' for local if config is missing.
        """
        config_file = "app_config.json"
        defaults = {"local_path": "2D_Storage", "network_path": ""}
        
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    # Backward Compatibility: Support legacy key "storage_path" 
                    # If "storage_path" exists but "network_path" doesn't, map it.
                    if "storage_path" in config and not "network_path" in config:
                        config["network_path"] = config["storage_path"]
                    
                    return {
                        "local_path": config.get("local_path", defaults["local_path"]),
                        "network_path": config.get("network_path", defaults["network_path"])
                    }
            except:
                return defaults
        return defaults

    def set_storage_config(self, local_path, network_path):
        """Updates the storage paths in app_config.json."""
        config_file = "app_config.json"
        config = {}
        
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except:
                config = {}
        
        config["local_path"] = local_path
        config["network_path"] = network_path
        
        # Remove legacy key to avoid confusion
        if "storage_path" in config:
            del config["storage_path"]
        
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)

    # Legacy alias for backward compatibility during transition
    def get_storage_path(self):
        return self.get_storage_config()["network_path"]

    def set_storage_path(self, path):
         # Assuming legacy set call implies network path update, keeping default local
         self.set_storage_config("2D_Storage", path)
            
    def sync_files(self):
        """Public method to trigger file synchronization."""
        print("Starting File Sync...")
        try:
            self._sync_files()
            return True, "File Sync Complete"
        except Exception as e:
            return False, str(e)

    def _sync_files(self):
        """
        Synchronizes files between Local Path and Network Path using shutil.
        This is a bidirectional sync:
        1. Pulls missing files from Network -> Local (Restores backup).
        2. Pushes missing files from Local -> Network (Backs up new files).
        """
        cfg = self.get_storage_config()
        local_dir = cfg["local_path"]
        net_dir = cfg["network_path"]
        
        # Validation: If network path not set, identical to local, or unreachable -> Skip
        if not net_dir or local_dir == net_dir or not os.path.exists(net_dir):
            return

        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
            
        # 1. Network -> Local (Pull Missing)
        for fname in os.listdir(net_dir):
            net_f = os.path.join(net_dir, fname)
            loc_f = os.path.join(local_dir, fname)
            if os.path.isfile(net_f):
                if not os.path.exists(loc_f):
                    shutil.copy2(net_f, loc_f)
                    print(f"Synced Down: {fname}")

        # 2. Local -> Network (Push Missing)
        for fname in os.listdir(local_dir):
            loc_f = os.path.join(local_dir, fname)
            net_f = os.path.join(net_dir, fname)
            if os.path.isfile(loc_f):
                if not os.path.exists(net_f):
                    shutil.copy2(loc_f, net_f)
                    print(f"Synced Up: {fname}")

    def calculate_sla_due_date(self, priority):
        """Calculates due date based on priority."""
        # Default SLAs (Minutes)
        slas = {
            "Critical": 240,   # 4 Hours
            "High": 480,       # 8 Hours
            "Medium": 1440,    # 24 Hours
            "Low": 4320        # 3 Days
        }
        minutes = slas.get(priority, 1440)
        return datetime.now() + timedelta(minutes=minutes)

    def create_ticket(self, asset_id, ticket_type, title, description, priority, logged_by, related_type=None, status='Open'):
        """
        Creates a new ticket with SLA due date.
        Returns: new_ticket_id (int) or None
        """
        try:
            due_date = self.calculate_sla_due_date(priority)
            
            # Cloud vs Local SQL
            if self.mode == "CLOUD":
                conn = self._get_cloud_conn()
                if not conn:
                    return None
                
                cursor = conn.cursor()
                sql = """
                    INSERT INTO tickets (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status))
                conn.commit()
                last_id = cursor.lastrowid
                conn.close()
                return last_id
            else:
                conn = self._get_local_conn()
                cursor = conn.cursor()
                sql = """
                    INSERT INTO tickets (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """
                cursor.execute(sql, (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status))
                conn.commit()
                last_id = cursor.lastrowid
                conn.close()
                return last_id
        except Exception as e:
            print(f"Error creating ticket: {e}")
            return None

    def create_ticket_with_assets(self, title, description, priority, status, assigned_to, due_date, asset_list, logged_by="User"):
        """
        Creates a ticket and links multiple assets to it.
        Args:
            asset_list: List of dicts [{'id': 1, 'type': 'computing_machine'}, ...]
        """
        print(f"Creating Ticket '{title}' with {len(asset_list)} assets...")
        
        # 1. Create the Ticket Parent Record
        # We need a primary asset for the main record (legacy support), pick the first one if available
        primary_asset_id = asset_list[0]['id'] if asset_list else None
        primary_asset_type = asset_list[0]['type'] if asset_list else None
        
        try:
            # We use the existing create_ticket method logic but slightly adapted / or just direct SQL here to include assigned_to
            # Let's do direct SQL to support new columns 'assigned_to'
            
            if self.mode == "CLOUD":
                conn = self._get_cloud_conn()
                cursor = conn.cursor()
                sql = """
                    INSERT INTO tickets (ticket_type, title, description, priority, status, logged_by, assigned_to, due_date, asset_id, related_type, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, ("Incident", title, description, priority, status, logged_by, assigned_to, due_date, primary_asset_id, primary_asset_type))
                conn.commit()
                ticket_id = cursor.lastrowid
                conn.close()
            else:
                # Local
                conn = self._get_local_conn()
                cursor = conn.cursor()
                sql = """
                    INSERT INTO tickets (ticket_type, title, description, priority, status, logged_by, assigned_to, due_date, asset_id, related_type, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """
                cursor.execute(sql, ("Incident", title, description, priority, status, logged_by, assigned_to, due_date, primary_asset_id, primary_asset_type))
                conn.commit()
                ticket_id = cursor.lastrowid
                conn.close()

            if not ticket_id:
                return False, "Failed to generate Ticket ID."

            # 2. Link Assets (ticket_assets table)
            if asset_list:
                if self.mode == "CLOUD":
                    sql_link = "INSERT INTO ticket_assets (ticket_id, asset_id, asset_type, created_at) VALUES (%s, %s, %s, NOW())"
                    for item in asset_list:
                         self.execute(sql_link, (ticket_id, item['id'], item['type']))
                else:
                    sql_link = "INSERT INTO ticket_assets (ticket_id, asset_id, asset_type, created_at) VALUES (?, ?, ?, datetime('now'))"
                    for item in asset_list:
                         self.execute(sql_link, (ticket_id, item['id'], item['type']))
            
            # Commit handled by execute usually if autocommit? 
            # execute wrapper doesn't explicitly commit unless we check.
            # Local execute commits. Cloud execute?
            # Let's force commit if needed. The wrapper _get_local_conn usually returns a connection that we commit on close?
            # Actually self.execute usually handles commit for INSERT/UPDATE if implied.
            # Checking execute implementation:
            # if self.mode == 'CLOUD': conn.commit() is called.
            # if self.mode == 'LOCAL': self.local_conn.commit() is called.
            # So we are good.
            
            return True, ticket_id
            
        except Exception as e:
            print(f"Create Ticket Error: {e}")
            return False, str(e)
                
        except Exception as e:
            print(f"Error creating ticket: {e}")
            return None

    def save_attachment(self, ticket_id, uploaded_file):
        """
        Saves an uploaded file to the local directory and records it in the database.
        Also attempts to save to the Network path immediately.
        
        Args:
            ticket_id (int): ID of the ticket.
            uploaded_file (UploadedFile): Streamlit uploaded file object.
            
        Returns:
            bool: True on success, False on failure.
        """
        try:
            cfg = self.get_storage_config()
            local_dir = cfg["local_path"]
            net_dir = cfg["network_path"]
            
            # 1. Ensure Local Directory Exists
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            
            # Sanitize filename
            safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', uploaded_file.name)
            
            # 2. Save File Locally
            local_path = os.path.join(local_dir, f"{ticket_id}_{safe_filename}")
            with open(local_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            # 3. Save to Network (Best Effort)
            if net_dir and net_dir != local_dir and os.path.exists(net_dir):
                try:
                    net_path = os.path.join(net_dir, f"{ticket_id}_{safe_filename}")
                    shutil.copy2(local_path, net_path)
                except Exception as e:
                    print(f"Network Save Failed: {e}")
                
            # 4. Insert Record
            if self.mode == "CLOUD":
                sql = "INSERT INTO ticket_attachments (ticket_id, file_name, file_path, uploaded_at) VALUES (%s, %s, %s, NOW())"
                self.execute(sql, (ticket_id, safe_filename, local_path))
            else:
                sql = "INSERT INTO ticket_attachments (ticket_id, file_name, file_path, uploaded_at) VALUES (?, ?, ?, datetime('now'))"
                self.execute(sql, (ticket_id, safe_filename, local_path))
                
            return True
        except Exception as e:
            print(f"Attachment Save Error: {e}")
            return False

            return False
        
    # --- COMPANION APP USER MANAGEMENT ---
    
    def get_companion_users(self):
        """
        Fetches all registered users for the Companion App.
        FORCED: Targets VPS (dubaytech_db) specifically.
        
        Returns:
            list[dict]: A list of user dictionaries.
        """
        conn = self._get_vps_conn()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, username, role, created_at FROM companion_users ORDER BY created_at DESC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"Error fetching users from VPS: {e}")
            return []

    def add_companion_user(self, username, password, role="user", full_name=""):
        """
        Creates a new user for the Companion App on the VPS.
        """
        if not pbkdf2_sha256:
            return False, "Passlib not installed. Cannot hash password."
            
        conn = self._get_vps_conn()
        if not conn:
            return False, "Could not connect to VPS database."

        try:
            cursor = conn.cursor()
            
            # Check for duplicate username
            cursor.execute("SELECT id FROM companion_users WHERE username=%s", (username,))
            if cursor.fetchone():
                conn.close()
                return False, "Username already exists on VPS."
            
            # Hash password using PBKDF2-SHA256
            pw_hash = pbkdf2_sha256.hash(password)
            
            sql = "INSERT INTO companion_users (username, password_hash, role, full_name, is_active) VALUES (%s, %s, %s, %s, TRUE)"
            cursor.execute(sql, (username, pw_hash, role, full_name))
            conn.commit()
            cursor.close()
            conn.close()
            return True, "User created successfully on VPS."
            
        except Exception as e:
            if conn: conn.close()
            return False, str(e)

    def update_companion_user_status(self, username, is_active):
        """
        Updates the active status of a Companion App user.
        """
        conn = self._get_vps_conn()
        if not conn:
             return False, "Could not connect to VPS database."
        
        try:
            cursor = conn.cursor()
            val = 1 if is_active else 0
            
            sql = "UPDATE companion_users SET is_active=%s WHERE username=%s"
            cursor.execute(sql, (val, username))
            conn.commit()
            
            cursor.close()
            conn.close()
            return True, f"User {'enabled' if is_active else 'disabled'} successfully."
        except Exception as e:
            if conn: conn.close()
            return False, str(e)
            
    def delete_companion_user(self, username):
        """
        Permanently removes a user from the companion_users table on the VPS.
        """
        conn = self._get_vps_conn()
        if not conn:
             return False, "Could not connect to VPS database."
        
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM companion_users WHERE username=%s LIMIT 1", (username,))
            conn.commit()
            cursor.close()
            conn.close()
            return True, "User deleted from VPS."
        except Exception as e:
            if conn: conn.close()
            return False, str(e)
            
    def update_companion_user_password(self, username, new_password):
        """
        Updates the password for an existing Companion App user.
        """
        if not pbkdf2_sha256:
            return False, "Passlib not installed. Cannot hash password."
            
        conn = self._get_vps_conn()
        if not conn:
             return False, "Could not connect to VPS database."
        
        try:
            cursor = conn.cursor()
            pw_hash = pbkdf2_sha256.hash(new_password)
            
            sql = "UPDATE companion_users SET password_hash=%s WHERE username=%s"
            cursor.execute(sql, (pw_hash, username))
            conn.commit()
            
            if cursor.rowcount == 0:
                conn.close()
                return False, "User not found or password unchanged."
                
            cursor.close()
            conn.close()
            return True, "Password updated successfully on VPS."
        except Exception as e:
            if conn: conn.close()
            return False, str(e)

    def _connect_to_source(self, config):
        """
        Helper to establish connection to a specific source config, handling SSH if needed.
        """
        # 1. Check if this host requires SSH
        use_ssh = False
        ssh_conf = self.secrets_override.get("ssh") if self.secrets_override else st.secrets.get("ssh")
        
        if ssh_conf and config['host'] == ssh_conf['host']:
            use_ssh = True
            
        if use_ssh:
             # Ensure Tunnel is open
             # We reuse the existing tunnel if it matches, or restart
             if not self.ssh_tunnel or self.ssh_tunnel.ssh_host != ssh_conf['host']:
                 if self.ssh_tunnel: self.ssh_tunnel.stop()
                 from utils.sshtunnel_helper import SSHTunnel
                 self.ssh_tunnel = SSHTunnel(
                    ssh_host=ssh_conf['host'],
                    ssh_user=ssh_conf['user'],
                    ssh_password=ssh_conf['password'],
                    remote_bind_address=('127.0.0.1', 3306)
                 )
                 self.ssh_local_port = self.ssh_tunnel.start()
            
             # Connect via Localhost
             conn_params = dict(config)
             conn_params['host'] = '127.0.0.1'
             conn_params['port'] = self.ssh_local_port
             return mysql.connector.connect(**conn_params)
        else:
            # Direct Connect
            return mysql.connector.connect(**config)

    # --- CLOUD REPLICATION ---
    def get_tables(self, source="PRIMARY"):
        """
        Fetches the list of tables from the specified cloud database.
        
        Args:
            source (str): "PRIMARY" or "SECONDARY"
            
        Returns:
            list[str]: List of table names. Raises Exception on error.
        """
        if "mysql" not in st.secrets or "mysql_backup" not in st.secrets:
            raise ValueError("Missing database secrets.")

        config = st.secrets["mysql"] if source == "PRIMARY" else st.secrets["mysql_backup"]
        
        conn = None
        try:
            conn = self._connect_to_source(config)
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            rows = cursor.fetchall()
            tables = [r[0] for r in rows]
            cursor.close()
            conn.close()
            return tables
        except Exception as e:
            if conn: conn.close()
            # Re-raise to let caller handle/display
            raise e

    def replicate_cloud_db(self, direction="PRIMARY_TO_SECONDARY", tables=None):
        """
        Replicates data between Primary and Secondary Cloud Databases.
        
        Args:
            direction (str): "PRIMARY_TO_SECONDARY" or "SECONDARY_TO_PRIMARY"
            tables (list, optional): Specific tables to sync. If None, syncs ALL tables found in Source.
            
        Returns:
            tuple: (success (bool), message (str))
        """
        if "mysql" not in st.secrets or "mysql_backup" not in st.secrets:
            return False, "Both [mysql] and [mysql_backup] secrets are required."

        primary_cfg = st.secrets["mysql"]
        secondary_cfg = st.secrets["mysql_backup"]
        
        # Determine Source and Target context for logging
        if direction == "PRIMARY_TO_SECONDARY":
            src_cfg = primary_cfg
            tgt_cfg = secondary_cfg
            src_label = "PRIMARY"
            lbl = "Primary -> Secondary"
        else:
            src_cfg = secondary_cfg
            tgt_cfg = primary_cfg
            src_label = "SECONDARY"
            lbl = "Secondary -> Primary"
            
        print(f"Starting Cloud Replication: {lbl}")
        
        # Determine Tables to Sync
        if not tables:
            # Fetch all from source
            try:
                tables = self.get_tables(src_label)
            except Exception as e:
                return False, f"Failed to fetch table list from {src_label}: {e}"
                
            if not tables:
                return False, f"No tables found in {src_label}."
            print(f"Auto-detected {len(tables)} tables to sync.")
        else:
            # Sync user provided list
            pass
                  
        src_conn = None
        tgt_conn = None
        
        try:
            # Connect using helper to handle SSH for EITHER side
            src_conn = self._connect_to_source(src_cfg)
            
            # NOTE: If we need SSH for BOTH, single tunnel object might be an issue if they are different hosts?
            # But usually Primary/Secondary imply different hosts. 
            # If one is SSH and one is Direct, we are fine.
            # If BOTH are SSH to SAME host (localhost), we are fine.
            # If BOTH are SSH to DIFFERENT hosts (rare setup for this app context), 
            # our simple self.ssh_tunnel singleton would thrash.
            # Assumption: Only VPS requires SSH. Hostek is Direct.
            
            # Wait, if we use the singleton self.ssh_tunnel, and we just connected to SRC (e.g. VPS),
            # and now we connect to TGT (Hostek), the tunnel remains up but unused.
            # If we connect to SRC (Hostek), tunnel is not started.
            # Then TGT (VPS) needs tunnel. _connect_to_source will start it.
            # This is fine.
            
            tgt_conn = self._connect_to_source(tgt_cfg)
            
            src_cur = src_conn.cursor(dictionary=True)
            tgt_cur = tgt_conn.cursor()
            
            # Disable FK checks on target for bulk load
            tgt_cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            
            success_count = 0
            
            for tbl in tables:
                try:
                    # 1. Fetch Source
                    src_cur.execute(f"SELECT * FROM `{tbl}`") # Backticks for safety
                    rows = src_cur.fetchall()
                    
                    if not rows: 
                        # Even if empty, we might want to ensure table exists on target?
                        # For now, skip empty data sync, but creating table schema is separate.
                        # Ideally, we should dump schema too.
                        # PROPOSAL: Use 'CREATE TABLE LIKE' if missing? 
                        # Let's try basic CREATE LIKE
                        try:
                            # Cross-server create like is hard without federation.
                            # We'll assume schema exists or we rely on 'REPLACE INTO' failing if table missing.
                            pass
                        except:
                            pass
                        continue
                    
                    # 2. Prep Insert
                    cols = list(rows[0].keys())
                    col_names = ", ".join([f"`{c}`" for c in cols])
                    placeholders = ", ".join(["%s"] * len(cols))
                    
                    # Using INSERT IGNORE to handle updates presence without overwriting
                    sql = f"INSERT IGNORE INTO `{tbl}` ({col_names}) VALUES ({placeholders})"
                    
                    # 3. Bulk Execute
                    data = [tuple(r.values()) for r in rows]
                    tgt_cur.executemany(sql, data)
                    print(f"Replicated {len(data)} rows for {tbl}")
                    success_count += 1
                    
                except Exception as e:
                    print(f"Error replicating {tbl}: {e}")
                    # If table doesn't exist on target, this will fail.
                    # We could try to create it, but getting schema structure across connection is complex in python.
                    # We will log it.
            
            tgt_cur.execute("SET FOREIGN_KEY_CHECKS=1;")
            tgt_conn.commit()
            return True, f"Replication Complete ({lbl}). Synced {success_count} tables."
            
        except Exception as e:
            return False, str(e)
        finally:
            if src_conn: src_conn.close()
            if tgt_conn: tgt_conn.close()

    def render_sidebar_status(self):
        """Renders the Cloud Connection status and Sync button in the Sidebar."""
        with st.sidebar:
            # Restore KPU Branding
            if os.path.exists("logo.png"):
                st.image("logo.png", use_container_width=True)
            elif os.path.exists("dubay_logo.png"):
                st.image("dubay_logo.png", use_container_width=True)
            st.divider()
            st.markdown("### ☁️ Connectivity")
            
            # Status Indicator
            if self.mode == "CLOUD":
                st.success(f"{self.status_msg}")
            else:
                st.warning(f"{self.status_msg}")
                if st.button("🔌 Reconnect Cloud", use_container_width=True, help="Force a connection test to the Cloud Database"):
                    if self._test_cloud_connection():
                        self.mode = "CLOUD"
                        self.status_msg = "🟢 Cloud Reconnected!"
                        st.rerun()
                    else:
                        st.error("Cloud still unreachable.")
                
                if st.button("🔄 System Reload", use_container_width=True, help="Complete re-initialization of the Database Manager"):
                    st.session_state.db_manager = DatabaseManager()
                    st.rerun()
            
            # Sync Button (Cloud Database)
            if st.button("🔄 Sync Cloud DB", use_container_width=True, key="sidebar_sync_cloud_btn"):
                with st.spinner("Syncing Cloud Data..."):
                    success, msg = self.sync()
                    if success:
                        st.success(f"✅ {msg}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            
            # File Sync Button (Network)
            if st.button("📂 Sync Files (Net)", use_container_width=True, help="Sync files between Local Cache and Network Path", key="sidebar_sync_files_btn"):
                with st.spinner("Syncing Files..."):
                    success, msg = self.sync_files()
                    if success:
                        st.toast(msg, icon="✅")
                    else:
                        st.error(f"❌ {msg}")

            st.divider()
            
            # --- App Suite Integration ---
            st.markdown("### 📱 App Suite")
            
            # Helper: Check Directory
            def check_dir(app_name):
                current_dir = os.getcwd()
                parent_dir = os.path.dirname(current_dir)
                return os.path.exists(os.path.join(parent_dir, app_name))

            # Helper: Check Port
            def is_port_open(port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5) # Fast timeout
                    return s.connect_ex(('localhost', port)) == 0

            # --- 2D SOC (Port 8502) ---
            if check_dir("2D_SOC"):
                if is_port_open(8502):
                    st.markdown("🟢 [**2D SOC**](http://localhost:8502)")
                else:
                    st.warning("🔴 **2D SOC** (Offline)")
                    st.caption("Run `streamlit run app.py` in `../2D_SOC`")
            else:
                st.error("❌ 2D SOC Not Found")
                st.caption("Clone `2D_SOC` to parent directory.")

            # --- 2D Pentester (Port 8503) ---
            if check_dir("2D_Pentester"):
                if is_port_open(8503):
                    st.markdown("🟢 [**2D Pentester**](http://localhost:8503)")
                else:
                    st.warning("🔴 **2D Pentester** (Offline)")
                    st.caption("Run `streamlit run app.py` in `../2D_Pentester`")
            else:
                st.error("❌ 2D Pentester Not Found")
                st.caption("Clone `2D_Pentester` to parent directory.")

    # --- POLICY MANAGEMENT ---
    def create_policy(self, name, category, summary, content):
        """Creates a new Governance Policy."""
        sql_cloud = "INSERT INTO policies (name, category, summary, content, created_at) VALUES (%s, %s, %s, %s, NOW())"
        sql_local = "INSERT INTO policies (name, category, summary, content, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
        
        try:
            if self.mode == "CLOUD":
                self.execute(sql_cloud, (name, category, summary, content))
            else:
                self.execute(sql_local, (name, category, summary, content))
            return True, "Policy Created Successfully"
        except Exception as e:
            return False, str(e)

    def get_policies(self):
        """Fetches all policies."""
        return self.execute("SELECT * FROM policies ORDER BY created_at DESC", fetch=True) or []

    def get_nist_controls(self):
        """Fetches all NIST controls for mapping."""
        # Ensure table exists first if not handled
        return self.execute("SELECT * FROM nist_controls ORDER BY id", fetch=True) or []
    
    def link_policy_to_nist(self, policy_id, nist_control_id):
        """Maps a policy to a NIST control."""
        # Check existence
        existing = self.execute(f"SELECT * FROM policy_nist_mappings WHERE policy_id={policy_id} AND nist_control_id='{nist_control_id}'", fetch=True)
        if existing: return True # Already linked
        
        sql_cloud = "INSERT INTO policy_nist_mappings (policy_id, nist_control_id) VALUES (%s, %s)"
        sql_local = "INSERT INTO policy_nist_mappings (policy_id, nist_control_id) VALUES (?, ?)"
        
        try:
            if self.mode == "CLOUD":
                self.execute(sql_cloud, (policy_id, nist_control_id))
            else:
                self.execute(sql_local, (policy_id, nist_control_id))
            return True
        except Exception as e:
            print(f"Link Error: {e}")
            return False

    def get_policy_mappings(self, policy_id):
        """Get linked NIST controls for a policy."""
        return self.execute(f"SELECT nist_control_id FROM policy_nist_mappings WHERE policy_id={policy_id}", fetch=True) or []

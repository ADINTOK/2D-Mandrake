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
    
    Attributes:
        mode (str): Current operating mode ("CLOUD" or "LOCAL").
        local_db (str): Path to the local SQLite database file.
        status_msg (str): User-facing status message describing connection state.
    """
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
        
        # Try Cloud First
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
            self.status_msg = "🟠 Offline Mode (Local Cache)"
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
        except:
            return False
        return False

    def _get_cloud_conn(self):
        """
        Establishes a connection to Cloud MySQL. Implement Failover.
        Priority: 1. [mysql] (Primary) -> 2. [mysql_backup] (Backpup)
        Supports SSH Tunneling if configured.
        """
        
        # Use explicit override if provided (fixes stale st.secrets cache)
        active_secrets = self.secrets_override if self.secrets_override else st.secrets

        def connect_with_ssh_check(config, is_vps=False):
            """Helper to handle connection with potential SSH wrapper"""
            
            # Check for SSH config if it's the VPS or marked for SSH
            # We assume 'mysql_backup' IS the VPS based on context, 
            # OR we check if [ssh] matches the host.
            
            use_ssh = False
            if 'ssh' in active_secrets and config['host'] == active_secrets['ssh']['host']:
                use_ssh = True
            
            # Cleanup old tunnel if exists and switching hosts/failure
            if self.ssh_tunnel and (not use_ssh or self.ssh_tunnel.ssh_host != config['host']):
                try: self.ssh_tunnel.stop() 
                except: pass
                self.ssh_tunnel = None

            db_host = config['host']
            db_port = config.get("port", 3306)

            # Establish Tunnel if needed
            if use_ssh:
                if not self.ssh_tunnel:
                    print(f"Opening SSH Tunnel to {db_host}...")
                    ssh_cfg = active_secrets['ssh']
                    try:
                        self.ssh_tunnel = SSHTunnel(
                            ssh_host=ssh_cfg['host'],
                            ssh_user=ssh_cfg['user'],
                            ssh_password=ssh_cfg['password'],
                            remote_bind_address=('127.0.0.1', 3306),
                            ssh_port=ssh_cfg.get('port', 22)
                        )
                        self.ssh_local_port = self.ssh_tunnel.start()
                        print(f"SSH Tunnel Established on Port {self.ssh_local_port}")
                    except Exception as e:
                        print(f"SSH Tunnel Failed: {e}")
                        return None
                
                # Override for localhost connection
                db_host = '127.0.0.1'
                db_port = self.ssh_local_port

            # Connect
            return mysql.connector.connect(
                host=db_host, 
                user=config['user'], 
                password=config['password'],
                database=config['database'], 
                port=db_port,
                connection_timeout=5
            )

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
                self.status_msg = "🟠 Offline Mode (Fallback)"
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
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )""")

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

        # --- Companion App Users (Local Cache) ---
        cur.execute("""CREATE TABLE IF NOT EXISTS companion_users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
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
                sql = """
                    INSERT INTO tickets (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                self.execute(sql, (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status))
                
                # Get ID
                rows = self.execute("SELECT LAST_INSERT_ID()", fetch=True)
                return rows[0]['LAST_INSERT_ID()'] if rows else None
            else:
                sql = """
                    INSERT INTO tickets (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """
                self.execute(sql, (asset_id, ticket_type, title, description, priority, logged_by, related_type, due_date, status))
                return self.cursor.lastrowid
                
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

    def add_companion_user(self, username, password, role="user"):
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
            
            sql = "INSERT INTO companion_users (username, password_hash, role) VALUES (%s, %s, %s)"
            cursor.execute(sql, (username, pw_hash, role))
            conn.commit()
            cursor.close()
            conn.close()
            return True, "User created successfully on VPS."
            
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

    # --- CLOUD REPLICATION ---
    def replicate_cloud_db(self, direction="PRIMARY_TO_SECONDARY"):
        """
        Replicates data between Primary and Secondary Cloud Databases.
        
        Args:
            direction (str): "PRIMARY_TO_SECONDARY" or "SECONDARY_TO_PRIMARY"
            
        Returns:
            tuple: (success (bool), message (str))
        """
        if "mysql" not in st.secrets or "mysql_backup" not in st.secrets:
            return False, "Both [mysql] and [mysql_backup] secrets are required."

        primary_cfg = st.secrets["mysql"]
        secondary_cfg = st.secrets["mysql_backup"]
        
        # Determine Source and Target
        if direction == "PRIMARY_TO_SECONDARY":
            src_cfg = primary_cfg
            tgt_cfg = secondary_cfg
            lbl = "Primary -> Secondary"
        else:
            src_cfg = secondary_cfg
            tgt_cfg = primary_cfg
            lbl = "Secondary -> Primary"
            
        print(f"Starting Cloud Replication: {lbl}")
        
        tables = ['assets', 'tickets', 'iso_controls', 'nist_controls', 'policies', 
                  'asset_controls', 'asset_nist_controls', 'policy_nist_mappings', 'ticket_attachments',
                  'kpu_business_services_level1', 'kpu_business_services_level2', 'kpu_technical_services', 
                  'kpu_enterprise_assets', 'kpu_component_assets', 'kpu_enterprise_software', 
                  'kpu_enterprise_computing_machines', 'companion_users']
                  
        src_conn = None
        tgt_conn = None
        
        try:
            # Connect
            src_conn = mysql.connector.connect(**src_cfg)
            tgt_conn = mysql.connector.connect(**tgt_cfg)
            
            src_cur = src_conn.cursor(dictionary=True)
            tgt_cur = tgt_conn.cursor()
            
            # Disable FK checks on target for bulk load
            tgt_cur.execute("SET FOREIGN_KEY_CHECKS=0;")
            
            for tbl in tables:
                try:
                    # 1. Fetch Source
                    src_cur.execute(f"SELECT * FROM {tbl}")
                    rows = src_cur.fetchall()
                    
                    if not rows: continue
                    
                    # 2. Prep Insert
                    cols = list(rows[0].keys())
                    col_names = ", ".join(cols)
                    placeholders = ", ".join(["%s"] * len(cols))
                    
                    # Using REPLACE INTO to handle updates/inserts
                    sql = f"REPLACE INTO {tbl} ({col_names}) VALUES ({placeholders})"
                    
                    # 3. Bulk Execute
                    data = [tuple(r.values()) for r in rows]
                    tgt_cur.executemany(sql, data)
                    print(f"Replicated {len(data)} rows for {tbl}")
                    
                except Exception as e:
                    print(f"Error replicating {tbl}: {e}")
            
            tgt_cur.execute("SET FOREIGN_KEY_CHECKS=1;")
            tgt_conn.commit()
            return True, f"Replication Complete ({lbl})"
            
        except Exception as e:
            return False, str(e)
        finally:
            if src_conn: src_conn.close()
            if tgt_conn: tgt_conn.close()

    def render_sidebar_status(self):
        """Renders the Cloud Connection status and Sync button in the Sidebar."""
        with st.sidebar:
            st.divider()
            st.markdown("### ☁️ Connectivity")
            
            # Status Indicator
            if self.mode == "CLOUD":
                st.success(f"{self.status_msg}")
            else:
                st.warning(f"{self.status_msg}")
            
            # Sync Button (Cloud Database)
            if st.button("🔄 Sync Cloud DB", use_container_width=True):
                with st.spinner("Syncing Cloud Data..."):
                    success, msg = self.sync()
                    if success:
                        st.success(f"✅ {msg}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
            
            # File Sync Button (Network)
            if st.button("📂 Sync Files (Net)", use_container_width=True, help="Sync files between Local Cache and Network Path"):
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

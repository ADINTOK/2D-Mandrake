import sqlite3
import mysql.connector
import streamlit as st
import os
import re

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
# =============================================================================

class DatabaseManager:
    """
    Manages hybrid database connections (Cloud MySQL + Local SQLite).
    
    Attributes:
        mode (str): Current operating mode ("CLOUD" or "LOCAL").
        local_db (str): Path to the local SQLite database file.
        status_msg (str): User-facing status message describing connection state.
    """
    def __init__(self):
        """
        Initializes the manager, tests cloud connection, and sets initial mode.
        Does NOT trigger a full sync automatically to prevent blocking; calls sync() if connected.
        """
        self.mode = "PENDING" # "CLOUD" or "LOCAL"
        self.local_db = "local_cache.db"
        self.status_msg = "Initializing..."
        
        # Try Cloud First
        if self._test_cloud_connection():
            self.mode = "CLOUD"
            self.status_msg = "🟢 Cloud Connected"
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
                self.status_msg = "🟢 Cloud Connected (Synced)"
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
        Establishes a connection to the Cloud MySQL database using Streamlit secrets.
        
        Returns:
            mysql.connector.connection.MySQLConnection: Connection object or None if secrets missing.
        """
        if 'mysql' not in st.secrets: return None
        cfg = st.secrets["mysql"]
        return mysql.connector.connect(
            host=cfg["host"], user=cfg["user"], password=cfg["password"],
            database=cfg["database"], port=cfg.get("port", 3306),
            connection_timeout=3 # Reduced to 3s for faster failover on firewalls
        )

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

        # We manually fetch tables and insert/replace
        tables = ['assets', 'tickets', 'iso_controls', 'nist_controls', 'policies', 
                  'asset_controls', 'asset_nist_controls', 'policy_nist_mappings', 'ticket_attachments']
        
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
        local_conn.close()

import streamlit as st
import importlib
import database_manager
# Force reload the module to pick up class changes immediately. 
# This is crucial in Streamlit dev mode to avoid stale class definitions.
importlib.reload(database_manager)
from database_manager import DatabaseManager
import os
import time
import mysql.connector

# =============================================================================
# Page: Settings
# =============================================================================
# Displays current application configuration, specifically Focus on Database.
# =============================================================================

import toml
# NOTE: We use 'toml' library for writing if available, or simple string formatting if not.
# Since we need to write back to secrets.toml. 

def load_toml(path):
    # Try tomllib (Python 3.11+) first for reading
    try:
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        # Fallback to 'toml' package if installed or basic read
        import toml
        return toml.load(path)

def save_toml(path, data):
    # Use toml package to write safely
    try:
        import toml
        with open(path, "w") as f:
            toml.dump(data, f)
    except ImportError:
        # Fallback: Simple custom dumper for basic needs
        with open(path, "w") as f:
            for section, conf in data.items():
                f.write(f"[{section}]\n")
                if isinstance(conf, dict):
                    for k, v in conf.items():
                        if isinstance(v, str):
                            f.write(f'{k} = "{v}"\n')
                        else:
                            f.write(f'{k} = {v}\n')
                f.write("\n")

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")

# Initialize DB Manager (Aggressive Refresh)
# We check for the existence of new methods (get_storage_config) to ensure
# we are not using a stale instance of DatabaseManager from session state.
# Robust Session State management to handle hot-reloads
if 'db_manager' in st.session_state:
    # Check if instance is stale (missing methods) or class changed
    try:
        if not hasattr(st.session_state.db_manager, 'get_companion_users'):
            raise AttributeError("Stale DB Manager logic")
    except AttributeError:
        # Force a hard reset by deleting the key
        del st.session_state.db_manager

# Force load current on-disk config to ensure DatabaseManager doesn't use stale st.secrets
secrets_path = ".streamlit/secrets.toml"
ondisk_config = {}
if os.path.exists(secrets_path):
    try:
        ondisk_config = load_toml(secrets_path)
    except Exception:
        pass

# Re-initialize if missing (or just deleted after a swap)
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager(secrets_override=ondisk_config)

st.header("Database Configuration")

c1, c2 = st.columns(2)

with c1:
    st.subheader("Cloud Connection (MySQL)")
    
    # --- Swap Logic ---
    if st.button("🔄 Swap Primary & Secondary Roles", help="Promote Backup to Primary and vice-versa. Updates secrets.toml."):
        secrets_path = ".streamlit/secrets.toml"
        if os.path.exists(secrets_path):
            try:
                data = load_toml(secrets_path)
                if "mysql" in data and "mysql_backup" in data:
                    # Swap
                    data["mysql"], data["mysql_backup"] = data["mysql_backup"], data["mysql"]
                    save_toml(secrets_path, data)
                    st.success("Configuration Swapped! Reloading...")
                    # Critical: Fully reset DB manager to pick up new config on init
                    if 'db_manager' in st.session_state:
                        del st.session_state.db_manager
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Cannot swap: Missing [mysql] or [mysql_backup] sections.")
            except Exception as e:
                st.error(f"Swap Failed: {e}")
        else:
            st.error("secrets.toml not found.")
            
    cloud_c1, cloud_c2 = st.columns(2)
    
    # Identify which host is which for the label
    hostek_ip = "213.109.159.7"
    vps_ip = "74.208.225.182"
    
    # --- Role 1 (Primary) ---
    with cloud_c1:
        if "mysql" in ondisk_config:
            secrets = ondisk_config["mysql"]
            curr_host = secrets.get("host", "")
            
            # Dynamic Label
            label = "Primary (Active)"
            if curr_host == hostek_ip: label += " - Hostek 🏠"
            elif curr_host == vps_ip: label += " - Linux VPS 🌐"
            
            st.markdown(f"#### {label}")
            
            st.text_input("Host Address", value=curr_host, disabled=True, key="p_host")
            st.text_input("Database Name", value=secrets.get("database", "Unknown"), disabled=True, key="p_db")
            st.text_input("Database User", value=secrets.get("user", "Unknown"), disabled=True, key="p_user")
            
            # DEBUG INFO
            ssh_host = ondisk_config.get("ssh", {}).get("host")
            is_ssh = (curr_host == ssh_host)
            st.caption(f"Backend Mode: {'🔐 SSH Tunnel' if is_ssh else '🔗 Direct Connection'}")
            
            if st.button("Test Primary Connection", key="test_primary"):
                # ... (rest stays the same)
                try:
                    # Use on-disk secrets to test immediately
                    conn_kwargs = secrets.copy()
                    
                    # Manual Tunnel handling for test button if needed? 
                    # Ideally DatabaseManager handles this. 
                    # For simple UI test, we might fail if tunnel needed but not running.
                    # But if we swapped to VPS, we NEED tunnel. 
                    # So we should rely on DatabaseManager's logic or replicate it slightly.
                    # SIMPLER: Use direct connect if possible, or warn.
                    # Actually better: Use DB Manager to test!
                    
                    # Re-implement simple check or use Manager?
                    # Using Manager is safer but might be stale.
                    # Let's try direct verify using our new helper if SSH.
                    
                    if is_ssh:
                        from utils.sshtunnel_helper import SSHTunnel
                        tunnel = SSHTunnel(
                            ssh_host=ssh_host,
                            ssh_user=ondisk_config["ssh"]["user"],
                            ssh_password=ondisk_config["ssh"]["password"],
                            remote_bind_address=('127.0.0.1', 3306)
                        )
                        local_port = tunnel.start()
                        conn_kwargs['host'] = '127.0.0.1'
                        conn_kwargs['port'] = local_port
                        
                        conn = mysql.connector.connect(**conn_kwargs, connection_timeout=5)
                        if conn.is_connected():
                            st.success("✅ Online (via Tunnel)")
                            conn.close()
                        tunnel.stop()
                    else:
                        conn = mysql.connector.connect(**secrets, connection_timeout=3)
                        if conn.is_connected():
                            st.success("✅ Online")
                            conn.close()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        else:
            st.error("Missing [mysql] in secrets.toml")

    # --- Role 2 (Secondary) ---
    with cloud_c2:
        if "mysql_backup" in ondisk_config:
            secrets_bak = ondisk_config["mysql_backup"]
            curr_host_bak = secrets_bak.get("host", "")
            
            # Dynamic Label
            label_bak = "Secondary (Backup)"
            if curr_host_bak == hostek_ip: label_bak += " - Hostek 🏠"
            elif curr_host_bak == vps_ip: label_bak += " - Linux VPS 🌐"
            
            st.markdown(f"#### {label_bak}")
            
            st.text_input("Host Address", value=curr_host_bak, disabled=True, key="s_host")
            st.text_input("Database Name", value=secrets_bak.get("database", "Unknown"), disabled=True, key="s_db")
            st.text_input("Database User", value=secrets_bak.get("user", "Unknown"), disabled=True, key="s_user")
            
            if st.button("Test Secondary Connection", key="test_secondary"):
                try:
                    # Check SSH for secondary too
                    ssh_host = ondisk_config.get("ssh", {}).get("host")
                    is_ssh_bak = (secrets_bak.get("host") == ssh_host)
                    
                    if is_ssh_bak:
                         from utils.sshtunnel_helper import SSHTunnel
                         tunnel = SSHTunnel(
                            ssh_host=ssh_host,
                            ssh_user=ondisk_config["ssh"]["user"],
                            ssh_password=ondisk_config["ssh"]["password"],
                            remote_bind_address=('127.0.0.1', 3306)
                        )
                         local_port = tunnel.start()
                         conn_bak = secrets_bak.copy()
                         conn_bak['host'] = '127.0.0.1'
                         conn_bak['port'] = local_port
                         
                         conn = mysql.connector.connect(**conn_bak, connection_timeout=5)
                         if conn.is_connected():
                             st.success("✅ Online (via Tunnel)")
                             conn.close()
                         tunnel.stop()
                    else:
                        conn = mysql.connector.connect(**secrets_bak, connect_timeout=3)
                        if conn.is_connected():
                            st.success("✅ Online")
                            conn.close()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        else:
            st.warning("No Backup Configured ([mysql_backup])")

    st.divider()
    st.markdown("#### 🔄 Cloud Replication (Primary ↔ Secondary)")
    
    rep_c1, rep_c2 = st.columns(2)
    with rep_c1:
        if st.button("➡️ Sync Primary to Secondary (Backup)", use_container_width=True):
            with st.spinner("Replicating: Hostek -> VPS..."):
                success, msg = st.session_state.db_manager.replicate_cloud_db("PRIMARY_TO_SECONDARY")
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")
                    
    with rep_c2:
        if st.button("⬅️ Sync Secondary to Primary (Restore)", use_container_width=True):
            with st.spinner("Replicating: VPS -> Hostek..."):
                success, msg = st.session_state.db_manager.replicate_cloud_db("SECONDARY_TO_PRIMARY")
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

with c2:
    st.subheader("Local Cache (SQLite)")
    db_path = "local_cache.db"
    
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_kb = size_bytes / 1024
        
        st.success(f"✅ Local Cache Active: `{db_path}`")
        st.metric("Cache Size", f"{size_kb:.2f} KB")

        net_path = st.session_state.db_manager.get_storage_path()
        if net_path and net_path != "2D_Storage":
             st.info(f"📂 Synced Network Path: `{net_path}`")
        else:
             st.caption("No custom network path configured.")
        
        if st.button("Force Sync Data (Cloud -> Local)"):
            with st.spinner("Syncing data..."):
                try:
                    st.session_state.db_manager._sync_data()
                    st.success("Sync Complete!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync Failed: {str(e)}")
    else:
        st.warning("Active Local Cache not found.")

st.divider()

st.header("🌍 Companion App Configuration")
st.info("Configuration for the client-facing support portal.")

comp_col1, comp_col2 = st.columns(2)

with comp_col1:
    st.subheader("Access Details")
    st.text_input("Public Access URL", value="http://74.208.225.182/dubay/2D_Mandrake/", disabled=True, key="comp_url")
    st.caption("Share this URL with end-users for ticket submission.")

with comp_col2:
    st.subheader("System Status")
    st.text_input("API Health Check", value="http://74.208.225.182/dubay/2D_Mandrake/api/status", disabled=True, key="comp_api")
    
    if st.button("Check Companion Status"):
        try:
            import requests
            response = requests.get("http://74.208.225.182/dubay/2D_Mandrake/api/status", timeout=2)
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Online: {data.get('app', 'Unknown App')}")
            else:
                st.error(f"❌ Error: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Connection Failed: {str(e)}")

st.header("👥 Companion App Users")
st.info("Manage users who can access the client-facing Support Portal. **Note: These users are stored permanently on the Linux VPS database.**")

# Check if VPS is reachable for user management
with st.spinner("Checking VPS User Database..."):
    # We can try to get users to confirm connection
    users = st.session_state.db_manager.get_companion_users()
    
    if st.session_state.db_manager.mode == "CLOUD" or users:
        # User List
        if users:
            # Convert to DataFrame for nice display or use columns
            for u in users:
                uc1, uc2, uc3, uc4 = st.columns([0.3, 0.2, 0.3, 0.2])
                with uc1:
                    st.markdown(f"**{u['username']}**")
                with uc2:
                    st.caption(f"{u['role']}")
                with uc3:
                    st.caption(f"Created: {u['created_at']}")
                with uc4:
                    if u['username'] != 'admin': # Prevent deleting admin
                        if st.button("🗑️ Delete", key=f"del_{u['username']}"):
                            success, msg = st.session_state.db_manager.delete_companion_user(u['username'])
                            if success:
                                st.success(f"Deleted {u['username']}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
                    else:
                        st.caption("Protected")

            with uc1:
                with st.expander(f"🔑 Reset Password: {u['username']}"):
                    new_pw = st.text_input("New Password", type="password", key=f"pw_{u['username']}")
                    if st.button("Update Password", key=f"btn_pw_{u['username']}"):
                        if new_pw:
                            success, msg = st.session_state.db_manager.update_companion_user_password(u['username'], new_pw)
                            if success:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            st.warning("Please enter a new password.")
            st.divider()
        else:
            st.warning("No users found or connection error.")

        # Add User Form
        st.subheader("Create New User")
        with st.form("new_user_form"):
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            
            if st.form_submit_button("Create User"):
                if new_user and new_pass:
                    success, msg = st.session_state.db_manager.add_companion_user(new_user, new_pass, new_role)
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("Username and Password are required.")

    else:
        st.warning("⚠️ Connect to Cloud Database to manage users.")
        if st.button("☁️ Retry Cloud Connection"):
            with st.spinner("Debug Connecting..."):
                try:
                    # 1. Check Secrets
                    if "mysql" not in st.secrets:
                        st.error("CRITICAL: 'mysql' section NOT found in st.secrets!")
                    else:
                        # 2. Direct Connect Attempt
                        cfg = st.secrets["mysql"]
                        # st.write(f"Attempting connect to: {cfg.get('host')}") 
                        conn = mysql.connector.connect(
                            host=cfg["host"],
                            user=cfg["user"], 
                            password=cfg["password"], 
                            database=cfg["database"],
                            port=cfg.get("port", 3306),
                            connection_timeout=5
                        )
                        
                        if conn.is_connected():
                            conn.close()
                            # Success - Update Manager
                            st.session_state.db_manager.mode = "CLOUD"
                            st.session_state.db_manager.status_msg = "🟢 Cloud Connected (Restored)"
                            st.success("✅ Connected Successfully! Reloading...")
                            time.sleep(1)
                            st.rerun()
                except Exception as e:
                    st.error(f"❌ Connection Failed: {str(e)}")
                    # Optional: Show traceback in expander
                    # st.exception(e)

st.divider()

st.header("🗂️ File Storage")
st.info("Configure where ticket attachments are stored.")

# Fetch current config
storage_cfg = st.session_state.db_manager.get_storage_config()
current_local = storage_cfg["local_path"]
current_network = storage_cfg["network_path"]

col_local, col_net = st.columns(2)

with col_local:
    new_local = st.text_input("Local Cache Path", value=current_local, help="Example: `2D_Storage` or `C:/App/Cache`")
    st.caption("Required. Used for offline access.")

with col_net:
    new_network = st.text_input("Network / Shared Storage Path", value=current_network, help="Example: `Z:/Shared/Tickets` or `//Server/Share`")
    st.caption("Optional. Used for backup and syncing.")

if st.button("Update Storage Configuration"):
    if new_local.strip():
        st.session_state.db_manager.set_storage_config(new_local.strip(), new_network.strip())
        st.success("✅ Storage paths updated!")
        
        # Validation Warnings
        if not os.path.exists(new_local.strip()):
             st.warning(f"Note: Local directory `{new_local}` does not exist yet. It will be created on first use.")
        if new_network.strip() and not os.path.exists(new_network.strip()):
             st.warning(f"Note: Network directory `{new_network}` not currently accessible.")
             
        # Force Reload to reflect changes if needed
        st.rerun()
    else:
        st.error("Local Path cannot be empty.")

c_sync1, c_sync2 = st.columns([0.3, 0.7])
with c_sync1:
    if st.button("🔄 Force File Sync (Local ↔ Network)"):
        with st.spinner("Syncing files..."):
            success, msg = st.session_state.db_manager.sync_files()
            if success:
                st.success(msg)
            else:
                st.error(f"Sync Failed: {msg}")

st.divider()

st.header("Application Info")
st.info(f"""
- **App Name**: 2D Mandrake
- **Environment**: {'Streamlit Cloud' if os.getenv('IS_STREAMLIT_CLOUD') else 'Local / On-Prem'}
- **Working Directory**: `{os.getcwd()}`
""")


import streamlit as st
import pandas as pd
import database_manager
import importlib
import time

# Force reload module
importlib.reload(database_manager)
from database_manager import DatabaseManager

st.set_page_config(page_title="DR DB Management", page_icon="🗄️", layout="wide")

st.title("🗄️ DR DB Management")
st.info("View and synchronize tables across Primary and Secondary database instances. This tool helps ensure schema integrity and data propagation.")

SYSTEM_TABLES = [
    "assets", "tickets", "ticket_assets", "ticket_attachments", "problems",
    "iso_controls", "asset_controls",
    "nist_controls", "asset_nist_controls", "policy_nist_mappings",
    "policies", "sla_policies",
    "kpu_business_services_level1", "kpu_business_services_level2",
    "kpu_technical_services",
    "kpu_enterprise_assets", "kpu_component_assets",
    "kpu_enterprise_software", "kpu_enterprise_computing_machines"
]

with st.expander("🔍 Debug Info (Connection)", expanded=False):
    st.write("Checking Secret Visibility:")
    if "ssh" in st.secrets:
        st.success("✅ [ssh] section found in st.secrets")
        st.write(f"SSH Host Configured: `{st.secrets['ssh'].get('host')}`")
    else:
        st.error("❌ [ssh] section MISSING in st.secrets")
        
    if "mysql" in st.secrets:
         st.write(f"Primary Host: `{st.secrets['mysql'].get('host')}`")
    
    if "db_manager" in st.session_state:
        mgr = st.session_state.db_manager
        st.write(f"DB Manager Mode: `{mgr.mode}`")
        if mgr.secrets_override:
            st.warning("⚠️ Using Secrets Override in DB Manager")
            st.write(f"Override Keys: {list(mgr.secrets_override.keys())}")
            if "ssh" in mgr.secrets_override:
                st.success("✅ SSH present in Override")
            else:
                st.error("❌ SSH missing in Override")
                
    if st.button("🔄 Hard Reset Connection Manager", type="primary"):
        if 'db_manager' in st.session_state:
            # Try to stop tunnel if exists
            try:
                if st.session_state.db_manager.ssh_tunnel:
                    st.session_state.db_manager.ssh_tunnel.stop()
            except: pass
            del st.session_state.db_manager
        st.success("Manager Reset. reloading...")
        time.sleep(1)
        st.rerun()
        
    st.markdown("---")
    st.write("🛠️ **Raw SQL Inspector**")
    sql_tgt = st.selectbox("Target DB", ["PRIMARY", "SECONDARY"])
    raw_sql = st.text_area("SQL Query", "SELECT DATABASE(), @@hostname, @@port;")
    
    if st.button("Run SQL"):
        try:
            db_mgr = st.session_state.db_manager
            # Creating a quick helper here using db_mgr internal concepts for debug
            
            cfg = st.secrets["mysql"] if sql_tgt == "PRIMARY" else st.secrets["mysql_backup"]
            conn = db_mgr._connect_to_source(cfg)
            cur = conn.cursor()
            cur.execute(raw_sql)
            res = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            st.dataframe(pd.DataFrame(res, columns=cols))
            conn.close()
        except Exception as e:
            st.error(f"SQL Error: {e}")

# Initialize DB Manager if not present OR if stale
if 'db_manager' in st.session_state:
    if not hasattr(st.session_state.db_manager, '_connect_to_source'):
        del st.session_state.db_manager

if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager

col1, col2 = st.columns(2)

primary_tables = []
secondary_tables = []

with col1:
    st.markdown("### ☁️ Primary Database")
    
    # Details
    if "mysql" in st.secrets:
        p_conf = st.secrets["mysql"]
        ssh_host = st.secrets.get("ssh", {}).get("host")
        conn_type = "🔐 SSH Tunnel" if ssh_host and p_conf.get('host') == ssh_host else "🔗 Direct Connection"
        st.caption(f"**Host:** `{p_conf.get('host')}` | **DB:** `{p_conf.get('database')}`")
        st.caption(f"**Type:** `{conn_type}`")
        if "SSH" in conn_type:
             st.caption(f"ℹ️ *To avoid SSH, open Port {p_conf.get('port', 3306)} and whitelist IP.*")
    else:
        st.caption("Active Production Source")

    if st.button("Refresh Primary", key="ref_pri", help="Reload the table list from the Live Primary Database."):
        st.rerun()
        
    with st.expander("🛠️ Advanced: Schema Repair"):
        st.info("Use this if tables are missing (RED x in System Table Usage). It creates empty tables.")
        if st.button("🔧 Initialize/Repair Core Schema (Primary)", type="secondary", help="Create missing System Tables in Primary DB. Does NOT overwrite existing data."):
            with st.spinner("Creating Missing Tables on Primary..."):
                ret_s, ret_msg = db.ensure_cloud_schema("PRIMARY")
                if ret_s:
                    st.success(ret_msg)
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(ret_msg)
        
    with st.spinner("Fetching Primary Tables..."):
        try:
            primary_tables = db.get_tables("PRIMARY")
            if primary_tables:
                # Add highlighting logic
                sys_set = set(["assets", "tickets", "ticket_assets", "ticket_attachments", "problems",
                    "iso_controls", "asset_controls",
                    "nist_controls", "asset_nist_controls", "policy_nist_mappings",
                    "policies", "sla_policies",
                    "kpu_business_services_level1", "kpu_business_services_level2",
                    "kpu_technical_services",
                    "kpu_enterprise_assets", "kpu_component_assets",
                    "kpu_enterprise_software", "kpu_enterprise_computing_machines"])

                data_p = []
                for t in primary_tables:
                    is_sys = "⭐ Core" if t in sys_set else ""
                    # Hidden sort key: (0 if core else 1, Name)
                    data_p.append({"Table Name": t, "Type": is_sys, "_sort": (0 if is_sys else 1, t)})
                
                # Sort
                data_p.sort(key=lambda x: x["_sort"])
                
                # Drop sort key for display
                for d in data_p: del d["_sort"]
                
                df_p = pd.DataFrame(data_p)
                st.dataframe(df_p, use_container_width=True, hide_index=True)
                
                core_count = len([t for t in primary_tables if t in sys_set])
                st.success(f"Found {len(primary_tables)} tables ({core_count} Core).")
            else:
                st.warning("Database is empty (0 tables).")
        except Exception as e:
            st.error(f"Connection Failed: {e}")
            st.caption("Common fixes: Check VPN, Firewall, or SSH Tunnel status.")

with col2:
    st.markdown("### 🛡️ Secondary Database")
    
    # Details
    if "mysql_backup" in st.secrets:
        s_conf = st.secrets["mysql_backup"]
        ssh_host = st.secrets.get("ssh", {}).get("host")
        conn_type_s = "🔐 SSH Tunnel" if ssh_host and s_conf.get('host') == ssh_host else "🔗 Direct Connection"
        st.caption(f"**Host:** `{s_conf.get('host')}` | **DB:** `{s_conf.get('database')}`")
        st.caption(f"**Type:** `{conn_type_s}`")
        if "SSH" in conn_type_s:
            st.caption(f"ℹ️ *To avoid SSH, open Port {s_conf.get('port', 3306)} and whitelist IP.*")
    else:
        st.caption("Backup / Failover Target")

    if st.button("Refresh Secondary", key="ref_sec", help="Reload the table list from the Backup Secondary Database."):
        st.rerun()

    with st.expander("🛠️ Advanced: Schema Repair"):
        st.info("Use this if tables are missing (RED x).")
        if st.button("🔧 Initialize/Repair Core Schema (Secondary)", key="rep_sec", type="secondary", help="Create missing System Tables in Backup DB."):
            with st.spinner("Creating Missing Tables on Secondary..."):
                ret_s, ret_msg = db.ensure_cloud_schema("SECONDARY")
                if ret_s:
                    st.success(ret_msg)
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(ret_msg)
        
    with st.spinner("Fetching Secondary Tables..."):
        try:
            secondary_tables = db.get_tables("SECONDARY")
            if secondary_tables:
                # Add highlighting logic
                sys_set = set(["assets", "tickets", "ticket_assets", "ticket_attachments", "problems",
                    "iso_controls", "asset_controls",
                    "nist_controls", "asset_nist_controls", "policy_nist_mappings",
                    "policies", "sla_policies",
                    "kpu_business_services_level1", "kpu_business_services_level2",
                    "kpu_technical_services",
                    "kpu_enterprise_assets", "kpu_component_assets",
                    "kpu_enterprise_software", "kpu_enterprise_computing_machines"])

                data_s = []
                for t in secondary_tables:
                     is_sys = "⭐ Core" if t in sys_set else ""
                     data_s.append({"Table Name": t, "Type": is_sys, "_sort": (0 if is_sys else 1, t)})

                # Sort
                data_s.sort(key=lambda x: x["_sort"])
                
                # Drop sort key
                for d in data_s: del d["_sort"]

                df_s = pd.DataFrame(data_s)
                st.dataframe(df_s, use_container_width=True, hide_index=True)
                
                core_count_s = len([t for t in secondary_tables if t in sys_set])
                st.success(f"Found {len(secondary_tables)} tables ({core_count_s} Core).")
            else:
                st.warning("Database is empty (0 tables).")
        except Exception as e:
             st.error(f"Connection Failed: {e}")

st.divider()

# Comparison Logic
if primary_tables and secondary_tables:
    set_p = set(primary_tables)
    set_s = set(secondary_tables)
    
    missing_in_sec = list(set_p - set_s)
    missing_in_pri = list(set_s - set_p)
    
    st.subheader("📊 Schema Comparison")
    
    c_diff1, c_diff2 = st.columns(2)
    
    with c_diff1:
        if missing_in_sec:
            st.error(f"Missing in Secondary ({len(missing_in_sec)}):")
            st.write(missing_in_sec)
        else:
            st.success("✅ Secondary has all Primary tables.")
            
    with c_diff2:
        if missing_in_pri:
            st.warning(f"Missing in Primary ({len(missing_in_pri)}):")
            st.write(missing_in_pri)
        else:
            st.success("✅ Primary has all Secondary tables.")

st.divider()

# ... (Keep existing code above)

st.divider()

st.subheader("🔄 Synchronization Tools")

# Global Actions
if st.button("🚀 Sync Core Tables Only", type="primary", help="Immediately sync all 19 system tables from Primary to Secondary"):
     # Filter SYSTEM_TABLES to those present in Primary
     valid_core = [t for t in SYSTEM_TABLES if t in primary_tables]
     if valid_core:
        with st.spinner("🚀 Syncing 3-Way (Primary->Secondary->Local)..."):
            # 1. Cloud
            s_cloud, m_cloud = db.replicate_cloud_db("PRIMARY_TO_SECONDARY", tables=valid_core)
            # 2. Local
            if s_cloud:
                s_loc, m_loc = db.sync()
                final_msg = f"{m_cloud}\n\n✅ Local: {m_loc}" if s_loc else f"{m_cloud}\n\n⚠️ Local Failed: {m_loc}"
                st.success(final_msg)
                time.sleep(3)
                st.rerun()
            else:
                st.error(m_cloud)
     else:
         st.warning("No Core System Tables found in Primary.")

sync_col1, sync_col2 = st.columns(2)

with sync_col1:
    st.markdown("#### Primary ➡️ Secondary")
    st.caption("Push data from Production to Backup.")
    
    # Selective Sync
    sel_tables_p = st.multiselect("Select Tables to Sync (P->S)", options=primary_tables, default=missing_in_sec if missing_in_sec else [])

    # Stage 1: Review
    if st.button("🔎 Review Sync Plan (P->S)"):
        if not sel_tables_p:
            st.warning("No tables selected.")
        else:
            st.session_state.sync_stage_p = "CONFIRM"
            st.session_state.sync_target_p = sel_tables_p
            st.rerun()

    # Stage 2: Confirm
    if st.session_state.get("sync_stage_p") == "CONFIRM":
        st.info(f"⚠️ You are about to sync **{len(st.session_state.sync_target_p)}** tables from **Primary** to **Secondary**.")
        st.write(st.session_state.sync_target_p)
        st.info("ℹ️ This will **ADD MISSING** records to the Secondary database. Existing data will **NOT** be overwritten.")
        
        c_conf1, c_conf2 = st.columns(2)
        with c_conf1:
            if st.button("✅ Confirm & Execute Sync", type="primary"):
                with st.spinner(f"Syncing {len(st.session_state.sync_target_p)} tables... (Cloud & Local)"):
                    # 1. Cloud Replication (Primary -> Secondary)
                    success_cloud, msg_cloud = db.replicate_cloud_db("PRIMARY_TO_SECONDARY", tables=st.session_state.sync_target_p)
                    
                    if success_cloud:
                        # 2. Local Sync (Cloud -> Local Cache)
                        success_local, msg_local = db.sync()
                        
                        final_msg = f"{msg_cloud}\n\n✅ Local Cache Updated ({msg_local})" if success_local else f"{msg_cloud}\n\n⚠️ Local Sync Failed: {msg_local}"
                        
                        st.success(final_msg)
                        st.session_state.sync_stage_p = None # Reset
                        time.sleep(3) # Give user time to read
                        st.rerun()
                    else:
                        st.error(msg_cloud)
        with c_conf2:
             if st.button("❌ Cancel", key="cancel_p"):
                 st.session_state.sync_stage_p = None
                 st.rerun()

    # Full Sync Option (Protected)
    with st.expander("⚠️ Force Full Sync (Advanced)"):
        if st.checkbox("I understand this will ADD MISSING records to Secondary"):
            if st.button("🚨 Sync ALL Tables"):
                 with st.spinner("Syncing ALL tables... (This may take a while)"):
                     success, msg = db.replicate_cloud_db("PRIMARY_TO_SECONDARY", tables=primary_tables)
                     if success:
                        st.success(msg)
                     else:
                        st.error(msg)

with sync_col2:
    st.markdown("#### Secondary ➡️ Primary")
    st.caption("Restore data from Backup to Production.")
    
    sel_tables_s = st.multiselect("Select Tables to Restore (S->P)", options=secondary_tables)
    
    # Stage 1: Review
    if st.button("🔎 Review Restore Plan (S->P)", help="Preview which tables will be copied from Backup to Production."):
        if not sel_tables_s:
            st.warning("No tables selected.")
        else:
            st.session_state.sync_stage_s = "CONFIRM"
            st.session_state.sync_target_s = sel_tables_s
            st.rerun()

    # Stage 2: Confirm
    if st.session_state.get("sync_stage_s") == "CONFIRM":
        st.info(f"⚠️ You are about to restore **{len(st.session_state.sync_target_s)}** tables from **Secondary** to **Primary**.")
        st.write(st.session_state.sync_target_s)
        st.warning("This will OVERWRITE data in the PRODUCTION Primary database.")
        
        c_conf_s1, c_conf_s2 = st.columns(2)
        with c_conf_s1:
            if st.button("✅ Confirm & Execute Restore", type="primary"):
                with st.spinner(f"Restoring {len(st.session_state.sync_target_s)} tables..."):
                    success, msg = db.replicate_cloud_db("SECONDARY_TO_PRIMARY", tables=st.session_state.sync_target_s)
                    if success:
                        st.success(msg)
                        st.session_state.sync_stage_s = None # Reset
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(msg)
        with c_conf_s2:
             if st.button("❌ Cancel", key="cancel_s"):
                 st.session_state.sync_stage_s = None
                 st.rerun()

st.divider()

# --- System Table Usage ---
st.subheader("🏗️ System Table Usage")
st.info("The following tables are actively used by the 2D Mandrake Application codebase.")

# Create comparison dataframe for System Tables
sys_data = []
for t in SYSTEM_TABLES:
    in_primary = "✅ Found" if t in primary_tables else "❌ Missing"
    in_secondary = "✅ Found" if t in secondary_tables else "❌ Missing"
    status_icon = "🟢" if t in primary_tables and t in secondary_tables else "🔴"
    
    sys_data.append({
        "Status": status_icon,
        "Table Name": t,
        "Primary DB": in_primary,
        "Secondary DB": in_secondary
    })

st.dataframe(
    pd.DataFrame(sys_data), 
    use_container_width=True,
    hide_index=True,
    column_config={
        "Status": st.column_config.TextColumn("State", width="small"),
        "Table Name": st.column_config.TextColumn("Core System Table", width="medium")
    }
)

import streamlit as st
from database_manager import DatabaseManager
import os

# =============================================================================
# Page: Settings
# =============================================================================
# Displays current application configuration, specifically Focus on Database.
# =============================================================================

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")

# Initialize DB Manager
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

st.header("Database Configuration")

c1, c2 = st.columns(2)

with c1:
    st.subheader("Cloud Connection (MySQL)")
    
    # Check if secrets are loaded
    if "mysql" in st.secrets:
        secrets = st.secrets["mysql"]
        
        # Display Info (Masked Password)
        st.text_input("Host", value=secrets.get("host", "Unknown"), disabled=True)
        st.text_input("Database", value=secrets.get("database", "Unknown"), disabled=True)
        st.text_input("User", value=secrets.get("user", "Unknown"), disabled=True)
        st.text_input("Password", value="********", disabled=True, type="password")
        
        # Connectivity Check
        if st.button("Test Cloud Connection"):
            try:
                # Force a fresh check
                conn = st.session_state.db_manager._get_cloud_conn()
                if conn and conn.is_connected():
                    st.success("✅ Connected to Cloud Database successfully!")
                    st.json({"Ping": "OK", "Server Info": conn.get_server_info()})
                else:
                    st.error("❌ Failed to connect to Cloud Database.")
            except Exception as e:
                st.error(f"❌ Connection Error: {str(e)}")
                
    else:
        st.warning("⚠️ No `[mysql]` section found in `.streamlit/secrets.toml`.")
        st.info("The app is likely running in **Offline Mode**.")

with c2:
    st.subheader("Local Cache (SQLite)")
    db_path = "local_cache.db"
    
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_kb = size_bytes / 1024
        
        st.success(f"✅ Local Cache Active: `{db_path}`")
        st.metric("Cache Size", f"{size_kb:.2f} KB")
        
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

st.header("Application Info")
st.info(f"""
- **App Name**: 2D Mandrake
- **Environment**: {'Streamlit Cloud' if os.getenv('IS_STREAMLIT_CLOUD') else 'Local / On-Prem'}
- **Working Directory**: `{os.getcwd()}`
""")

import streamlit as st
import os

st.set_page_config(page_title="Documentation", page_icon="📚", layout="wide")

st.title("📚 Application Documentation")
st.info("""
**The Operational Blueprint**
Centralized repository for technical specifications, user guides, and ITIL standards. 
This handbook serves as the "Ground Truth" for administrators and developers, 
documenting everything from the hierarchical data model to the live database schema.
Maintain operational consistency by following these standardized procedures.
""")

def read_file(filename):
    """Reads a markdown file from the root directory."""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return f"⚠️ Error: `{filename}` not found."

from database_manager import DatabaseManager

# Initialize Database Manager
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

# Global Sidebar: Connectivity & Sync Controls
st.session_state.db_manager.render_sidebar_status()

# Create tabs for different documentation sources
tab_guide, tab_walk, tab_user, tab_portal, tab_tech, tab_schema = st.tabs(["🔰 ITIL & ISO Primer", "🚀 Walkthrough", "📖 User Guide", "🌐 Self-Service Portal", "⚙️ Technical Specs", "🗄️ Live Schema"])

with tab_guide:
    st.markdown(read_file("ITIL_GUIDE.md"))
    st.markdown(read_file("README.md"))

with tab_tech:
    st.markdown(read_file("TECHNICAL_DOCS.md"))

with tab_portal:
    st.header("🌐 Companion App / Self-Service Portal")
    st.info("A separate light-weight web portal is available for end-users to submit tickets and view knowledge base articles without accessing this admin console.")
    
    st.markdown("""
    ### Access Details
    - **URL**: [http://74.208.225.182/dubay/2D_Mandrake/](http://74.208.225.182/dubay/2D_Mandrake/)
    - **Purpose**: End-User Ticket Submission & Status View
    - **Framework**: Python NiceGUI
    - **Hosted On**: Same VPS, connecting to `dubaytech_db`.
    
    ### Management
    The app runs as a systemd service on the Linux server.
    - **Restart**: `systemctl restart companion.service`
    - **Logs**: `journalctl -u companion.service -f`
    """)

with tab_walk:
    # Attempt to read from Artifacts if local file not present, or fallback
    # Since we saved walkthrough.md in Brain, we might need to copy it or read absolute.
    # For now, let's assume we want to read the local copy if we move it there, 
    # OR we can hardcode the path to the artifact for this dev session.
    # Ideally, we should copy the artifact to the app dir.
    # Let's try reading a local "WALKTHROUGH.md" and I'll copy the artifact content there.
    st.markdown(read_file("WALKTHROUGH.md"))

with tab_schema:
    st.subheader("Live Database Schema")
    st.caption("Inspect the current structure of the connected database.")
    
    if 'db_manager' in st.session_state:
        db = st.session_state.db_manager
        
        # Get tables based on mode
        tables = []
        try:
            if db.mode == "CLOUD":
                conn = db._get_cloud_conn()
                cur = conn.cursor()
                cur.execute("SHOW TABLES")
                tables = [t[0] for t in cur.fetchall()]
                conn.close()
            else:
                conn = db._get_local_conn()
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [t[0] for t in cur.fetchall()]
                conn.close()
                
            if tables:
                selected_table = st.selectbox("Select Table to Inspect", tables)
                
                if selected_table:
                    # Fetch columns/schema info
                    schema_data = []
                    if db.mode == "CLOUD":
                        conn = db._get_cloud_conn()
                        cur = conn.cursor()
                        cur.execute(f"DESCRIBE {selected_table}")
                        rows = cur.fetchall()
                        # MySQL Describe: Field, Type, Null, Key, Default, Extra
                        schema_data = [{"Column": r[0], "Type": r[1], "Key": r[3], "Extra": r[5]} for r in rows]
                        conn.close()
                    else:
                        conn = db._get_local_conn()
                        cur = conn.cursor()
                        cur.execute(f"PRAGMA table_info({selected_table})")
                        rows = cur.fetchall()
                        # SQLite Pragma: cid, name, type, notnull, dflt_value, pk
                        schema_data = [{"Column": r[1], "Type": r[2], "PK": "Yes" if r[5] else ""} for r in rows]
                        conn.close()
                        
                    st.dataframe(schema_data, use_container_width=True)
            else:
                st.warning("No tables found.")
        except Exception as e:
            st.error(f"Could not fetch schema: {e}")
    else:
        st.warning("Database Manager not initialized. Please visit the Home page first.")

import streamlit as st
import os

st.set_page_config(page_title="Documentation", page_icon="📚", layout="wide")

st.title("📚 Application Documentation")

def read_file(filename):
    """Reads a markdown file from the root directory."""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return f"⚠️ Error: `{filename}` not found."

# Create tabs for different documentation sources
tab_user, tab_tech, tab_schema = st.tabs(["📖 User Guide", "⚙️ Technical Specs", "🗄️ Live Schema"])

with tab_user:
    st.markdown(read_file("README.md"))

with tab_tech:
    st.markdown(read_file("TECHNICAL_DOCS.md"))

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

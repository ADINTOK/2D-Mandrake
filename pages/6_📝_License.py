import streamlit as st

st.set_page_config(page_title="License - 2D_Mandrake", page_icon="📝")

st.title("📝 User Agreement & License")

from database_manager import DatabaseManager
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()
    
# Global Sidebar: Connectivity & Sync Controls
st.session_state.db_manager.render_sidebar_status()

try:
    with open("LICENSE.md", "r", encoding="utf-8") as f:
        license_text = f.read()
    st.markdown(license_text)
    
    st.divider()
    st.info("By using this software, you agree to the terms above.")
    
except FileNotFoundError:
    st.error("LICENSE.md file not found.")

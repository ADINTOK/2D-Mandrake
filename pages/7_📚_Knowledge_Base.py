import streamlit as st
from database_manager import DatabaseManager
import time

# =============================================================================
# Page: Knowledge Base
# =============================================================================
# Allows users to create, search, and view Knowledge Articles (Solutions).
# Features:
# - Full Text Search
# - Markdown Support
# - "Copy Link" for easy sharing
# =============================================================================

st.set_page_config(page_title="Knowledge Base", page_icon="📚", layout="wide")

st.title("📚 Knowledge Base")

# Initialize DB
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()
    
# Render Sidebar (Status/Apps)
st.session_state.db_manager.render_sidebar_status()

db = st.session_state.db_manager

# --- Actions ---
# 1. Create Article
with st.expander("➕ Create New Article"):
    with st.form("new_article_form"):
        new_title = st.text_input("Title")
        new_category = st.selectbox("Category", ["General", "Hardware", "Software", "Network", "Security", "Process"])
        new_content = st.text_area("Content (Markdown Supported)", height=300)
        new_tags = st.text_input("Tags (comma separated)", help="e.g. wifi, password, printer")
        
        submitted = st.form_submit_button("Publish Article")
        if submitted:
            if new_title and new_content:
                try:
                    # Cloud vs Local SQL
                    if db.mode == "CLOUD":
                        sql = """
                            INSERT INTO knowledge_articles (title, category, content, tags, author, created_at)
                            VALUES (%s, %s, %s, %s, 'Admin', NOW())
                        """
                        db.execute(sql, (new_title, new_category, new_content, new_tags))
                    else:
                        sql = """
                            INSERT INTO knowledge_articles (title, category, content, tags, author, created_at)
                            VALUES (?, ?, ?, ?, 'Admin', datetime('now'))
                        """
                        db.execute(sql, (new_title, new_category, new_content, new_tags))
                    
                    st.success("✅ Article Published!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error publishing article: {e}")
            else:
                st.error("Title and Content are required.")

st.divider()

# --- Search & View ---
c1, c2 = st.columns([3, 1])
with c1:
    search_term = st.text_input("🔍 Search Knowledge Base", placeholder="How to reset password...")
with c2:
    filter_cat = st.selectbox("Filter Category", ["All", "General", "Hardware", "Software", "Network", "Security", "Process"])

# Query Construction
params = []
sql = "SELECT * FROM knowledge_articles WHERE 1=1"

if search_term:
    search_pattern = f"%{search_term}%"
    if db.mode == "CLOUD":
        sql += " AND (title LIKE %s OR content LIKE %s OR tags LIKE %s)"
        params.extend([search_pattern, search_pattern, search_pattern])
    else:
        sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])

if filter_cat != "All":
    if db.mode == "CLOUD":
        sql += " AND category = %s"
        params.append(filter_cat)
    else:
        sql += " AND category = ?"
        params.append(filter_cat)

sql += " ORDER BY created_at DESC"

# Fetch Results
try:
    articles = db.execute(sql, tuple(params), fetch=True)
except Exception as e:
    # If table doesn't exist (migration failed), catch it
    st.error(f"Database Error: {e}")
    articles = []

if articles:
    for art in articles:
        # Unpack dict
        a_id = art['id']
        title = art['title']
        cat = art['category']
        preview = art['content'][:200] + "..." if len(art['content']) > 200 else art['content']
        tags = art['tags']
        date = art['created_at']
        
        with st.container(border=True):
            c_head, c_meta = st.columns([0.8, 0.2])
            with c_head:
                st.subheader(f"{title}")
            with c_meta:
                st.caption(f"{cat} • {date}")
            
            st.markdown(preview)
            
            # View Full Logic (using Session State to toggle view not shown for brevity, 
            # usually simpler to just use an expander for 'Read More')
            with st.expander("📖 Read Full Article"):
                st.markdown(art['content'])
                st.caption(f"Tags: {tags}")
                st.code(f"KB-{a_id}: {title}") # Fake permalink ID
else:
    st.info("No articles found matching your search.")
    if not search_term:
         st.markdown("Try creating your first article above! 👆")

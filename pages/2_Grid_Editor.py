
import streamlit as st
import pandas as pd
from database_manager import DatabaseManager

# =============================================================================
# Page: Grid Editor
# =============================================================================
# Provides a high-efficiency spreadsheet access to Bulk Edit assets.
# Users can Add, Update, and Delete child assets of a selected parent.
# Uses Streamlit's experimental data_editor for in-place editing.
# =============================================================================

# Page Configuration
# Grid Editor allows bulk management of child assets for a selected parent.
st.set_page_config(page_title="Grid Editor", page_icon="✏️", layout="wide")

# Initialize Database Manager if accessed directly
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

def execute_query(query, params=None, fetch=False):
    """Executes a query using the global DB manager."""
    return st.session_state.db_manager.execute(query, params, fetch)

st.title("✏️ Grid Editor")

# --- Retrieve Parent ID ---
# The ID of the container (Category, System, etc.) is passed via query params.
try:
    qp = st.query_params
    parent_id = qp.get("id")
except:
    try:
        qp = st.experimental_get_query_params()
        parent_id = qp.get("id", [None])[0]
    except:
        parent_id = None

if not parent_id:
    st.info("👋 Please select a Category or Group from the **Home** page to edit its contents.")
    st.page_link("app.py", label="Go Home", icon="🏠")
else:
    # 1. Fetch Parent Details
    parent = execute_query("SELECT * FROM assets WHERE id = %s", (parent_id,), fetch=True)
    
    if not parent:
        st.error(f"Asset ID {parent_id} not found.")
    else:
        parent = parent[0]
        st.subheader(f"Editing Children of: {parent.get('name')} ({parent.get('type')})")
        
        # 2. Fetch Children for Editing
        # We fetch ID so we know what to UPDATE vs INSERT
        sql = "SELECT id, name, type, description FROM assets WHERE parent_id = %s ORDER BY name"
        children = execute_query(sql, (parent_id,), fetch=True)
        
        # Unified DataFrame Creation
        if children:
            df = pd.DataFrame(children)
        else:
            # Create empty DataFrame with correct column structure for new entries
            df = pd.DataFrame(columns=["id", "name", "type", "description"])
            
        # 3. Configure Data Editor
        # Column config controls inputs (e.g., Dropdown for Type)
        column_config = {
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Asset Name", required=True),
            "type": st.column_config.SelectboxColumn(
                "Type",
                options=["Asset", "Group", "Category", "System", "Service"],
                required=True
            ),
            "description": st.column_config.TextColumn("Description"),
        }
        
        with st.form("grid_edit_form"):
            if df.empty:
                st.info("No existing children. Add new assets below.")
                
            # `data_editor` allows in-place editing, row addition, and deletion.
            edited_df = st.data_editor(
                df,
                column_config=column_config,
                use_container_width=True,
                num_rows="dynamic", # Enables Add/Delete rows
                key="asset_editor"
            )
            
            # 4. Save Logic
            if st.form_submit_button("💾 Save Changes"):
                count_upd = 0
                count_add = 0
                count_del = 0
                
                # A. Detect Deletions
                # If an ID was in original but not in edited_df, it was deleted.
                # Handle empty original case
                if not df.empty:
                    new_ids = set(edited_df['id'].dropna().astype(int).tolist())
                    original_ids = set(df['id'].tolist())
                    deleted_ids = original_ids - new_ids
                    
                    if deleted_ids:
                        for uid in deleted_ids:
                            execute_query("DELETE FROM assets WHERE id=%s", (uid,))
                            count_del += 1
                        
                # B. Process Updates & Inserts
                for index, row in edited_df.iterrows():
                    aid = row.get('id')
                    aname = row.get('name')
                    atype = row.get('type')
                    adesc = row.get('description')
                    
                    # Check for NaN or None for ID to determine if it's new
                    is_new = pd.isna(aid) or aid == None
                    
                    if is_new:
                        # INSERT: No ID means it's a new row
                        if aname and atype: # Basic validation
                            execute_query(
                                "INSERT INTO assets (name, parent_id, type, description, created_at) VALUES (%s, %s, %s, %s, NOW())", 
                                (aname, parent_id, atype, adesc)
                            )
                            count_add += 1
                    else:
                        # UPDATE: Existing ID
                        execute_query(
                            "UPDATE assets SET name=%s, type=%s, description=%s WHERE id=%s",
                            (aname, atype, adesc, aid)
                        )
                        count_upd += 1 
                        
                st.success(f"Saved! (Added: {count_add}, Deleted: {count_del}, Processed: {count_upd})")
                st.rerun()

    st.markdown("---")
    st.page_link("app.py", label="Back to Hierarchy", icon="⬅️")

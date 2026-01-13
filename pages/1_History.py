import streamlit as st
import pandas as pd
from database_manager import DatabaseManager

# =============================================================================
# Page: Ticket History
# =============================================================================
# Displays a detailed audit log of tickets for a specific asset.
# Includes functionality to browse ticket details and download attachments.
# =============================================================================

# Page Configuration
# 'Ticket History' allows users to see the audit log of specific assets.
st.set_page_config(page_title="Ticket History", page_icon="📜", layout="wide")

# Initialize Database Manager if accessed directly
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

def execute_query(query, params=None, fetch=False):
    """Executes a query using the global DB manager."""
    return st.session_state.db_manager.execute(query, params, fetch)

st.title("📜 Ticket History")

# --- Retreive Asset ID ---
# The ID is passed via query parameters from the main Hierarchy Explorer.
# We support both the deprecated and new Streamlit APIs for compatibility.
try:
    # Try modern way (Streamlit 1.30+)
    qp = st.query_params
    asset_id = qp.get("id")
except:
    # Fallback for older versions
    try:
        qp = st.experimental_get_query_params()
        asset_id = qp.get("id", [None])[0]
    except:
        asset_id = None

# Logic checks
if not asset_id:
    st.info("👋 Please select an asset from the **Home** page to view its history.")
    st.page_link("app.py", label="Go Home", icon="🏠")
else:
    # 1. Fetch Asset Details
    asset = execute_query("SELECT * FROM assets WHERE id = %s", (asset_id,), fetch=True)
    
    if not asset:
        st.error(f"Asset ID {asset_id} not found.")
    else:
        # 2. Display Asset Header
        asset = asset[0]
        st.subheader(f"{asset.get('name', 'Unknown Asset')} ({asset.get('type')})")
        
        if asset.get('description'):
            st.caption(asset['description'])
            
        st.divider()
        
        # 3. Fetch History Logs
        sql = """
            SELECT t.id, t.created_at, t.ticket_type, t.priority, t.status, t.title, t.description, t.logged_by
            FROM tickets t
            WHERE t.asset_id = %s
            ORDER BY t.created_at DESC
        """
        history = execute_query(sql, (asset_id,), fetch=True)
        
        if history:
            # A. Summary Table
            st.markdown("### Ticket Log")
            df = pd.DataFrame(history)
            st.dataframe(
                df[['id', 'created_at', 'status', 'priority', 'ticket_type', 'title', 'logged_by']], 
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            
            # B. Detail View (Attachments)
            st.markdown("### Ticket Details & Attachments")
            
            # Select Box to choose ticket
            ticket_options = [f"#{row['id']} - {row['title']} ({row['created_at']})" for row in history]
            # Map back to ID
            selected_option = st.selectbox("Select Ticket to View Files:", options=ticket_options)
            
            if selected_option:
                # Parse ID from string (e.g. "#123 - ...")
                # Simple split
                sel_id = int(selected_option.split('#')[1].split(' ')[0])
                
                # Find the full record for description
                record = next((r for r in history if r['id'] == sel_id), None)
                
                if record:
                    st.info(f"**Description**: {record['description']}")
                    
                    # Fetch Attachments
                    att_sql = "SELECT * FROM ticket_attachments WHERE ticket_id = %s"
                    attachments = execute_query(att_sql, (sel_id,), fetch=True)
                    
                    if attachments:
                        st.write("**Attached Files:**")
                        for att in attachments:
                            c1, c2 = st.columns([4, 1])
                            c1.text(f"📄 {att['file_name']} (Uploaded: {att['uploaded_at']})")
                            
                            # Download Button
                            # Helper to read file safely
                            file_path = att['file_path']
                            try:
                                with open(file_path, "rb") as f:
                                    btn = c2.download_button(
                                        label="Download",
                                        data=f,
                                        file_name=att['file_name'],
                                        mime="application/octet-stream",
                                        key=f"dl_{att['id']}"
                                    )
                            except FileNotFoundError:
                                c2.error("File missing from disk")
                    else:
                        st.caption("No attachments found for this ticket.")

            st.success(f"Found {len(history)} tickets.")
        else:
            st.info("No tickets recorded for this asset.")

    # Navigation Footer
    st.markdown("---")
    st.page_link("app.py", label="Back to Hierarchy", icon="⬅️")

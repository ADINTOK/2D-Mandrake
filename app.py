import streamlit as st
import mysql.connector
import pandas as pd
import os
import shutil
import graphviz
from datetime import datetime

# =============================================================================
# 2D Mandrake - Asset & Ticketing Management System
# =============================================================================
# This is the main entry point for the Streamlit application.
# It handles the Sidebar Navigation, Dashboard, Hierarchy Explorer,
# and Ticket Management (creation, viewing, and file attachments).
#
# Key Features:
# - Connects to MySQL (Cloud) or SQLite (Local) via DatabaseManager.
# - Renders a recursive Asset Tree (Hierarchy Explorer).
# - Provides Ticketing (ITIL based: Incident, Request, Change, Problem).
# - Supports file uploads for Tickets.
# =============================================================================

# Page Configuration
# Sets the browser tab title, icon, and wide layout for better data visibility
st.set_page_config(
    page_title="2D Mandrake",
    page_icon="🔧",
    layout="wide"
)

# --- Database Manager Integration ---
from database_manager import DatabaseManager

# Initialize Singleton Database Manager
# Stores the manager in session_state to persist connection across reruns
if 'db_manager' not in st.session_state:
    with st.spinner("Connecting to Database (Cloud/Local)..."):
        st.session_state.db_manager = DatabaseManager()

def execute_query(query, params=None, fetch=False):
    """
    Wrapper for executing SQL queries using the robust DatabaseManager.
    
    Args:
        query (str): The SQL query string.
        params (tuple, optional): Parameters to substitute into the query.
        fetch (bool): If True, returns the fetched results as a list of dicts.
        
    Returns:
        list/bool: Rows if fetch=True, otherwise success boolean.
    """
    return st.session_state.db_manager.execute(query, params, fetch)

# --- Sidebar Status ---
# Displays current connection status (Cloud vs Local)
st.sidebar.caption(f"DB Status: {st.session_state.db_manager.status_msg}")

# Sync Button
# Allows manual synchronization of data from Cloud to Local cache
if st.sidebar.button("🔄 Sync with Cloud"):
    with st.spinner("Syncing data..."):
        success, msg = st.session_state.db_manager.sync()
        if success:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)

def fetch_hierarchy():
    """
    Fetches the entire asset list from the database.
    Includes a subquery count of associated changes for each asset.
    """
    sql = """
        SELECT a.*, 
               (SELECT COUNT(*) FROM tickets t WHERE t.asset_id = a.id AND t.status != 'Closed') as active_tickets 
        FROM assets a 
        ORDER BY a.type, a.name
    """
    return execute_query(sql, fetch=True) or []

def create_ticket(asset_id, t_type, title, desc, priority, status, user):
    """
    Creates a new ticket and returns its newly generated ID (or False).
    
    Args:
        asset_id (int): The Asset this ticket is related to.
        t_type (str): Incident, Change, Request, etc.
        title (str): Brief summary.
        desc (str): Full details.
        priority (str): Criticality level.
        status (str): Lifecycle state (Open, Closed).
        user (str): Who logged it.
        
    Returns:
        tuple: (Success (bool), Ticket ID (int) OR Error Message (str))
    """
    sql = """INSERT INTO tickets (asset_id, ticket_type, title, description, priority, status, logged_by, created_at, updated_at) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())"""
    try:
        # We need the ID of the inserted ticket to attach files
        # Using execute with a commit usually doesn't return ID directly in this wrapper structure
        # So we trust the LastRowID mechanism of the cursor if checking it, 
        # OR we select MAX(id) (risky in concurrency)
        # Better: Update DB Manager to return ID on insert, but for now we'll do a quick fetch
        execute_query(sql, (asset_id, t_type, title, desc, priority, status, user))
        
        # Immediate fetch back (simplest for this architecture)
        res = execute_query("SELECT MAX(id) as id FROM tickets", fetch=True)
        if res:
            return True, res[0]['id']
        return False, "Failed to retrieve new ticket ID"
    except Exception as e:
        return False, str(e)

def save_attachment(ticket_id, uploaded_file):
    """
    Saves an uploaded file to the local disk and records it in the DB.
    
    Args:
        ticket_id (int): The ticket to attach to.
        uploaded_file (UploadedFile): Streamlit file object.
        
    Returns:
        bool: Success status.
    """
    upload_dir = "2D_Storage"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        
    # Secure filename to avoid overwrites or path traversal (basic)
    safe_name = f"{ticket_id}_{uploaded_file.name}"
    file_path = os.path.join(upload_dir, safe_name)
    
    try:
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        sql = "INSERT INTO ticket_attachments (ticket_id, file_name, file_path) VALUES (%s, %s, %s)"
        execute_query(sql, (ticket_id, uploaded_file.name, file_path))
        return True
    except Exception as e:
        return False

def fetch_asset_history(asset_id, limit=20):
    """
    Retrieves the most recent change logs for a specific asset.
    Used for the History view.
    """
    sql = """
        SELECT c.id, c.created_at, c.change_type, c.impact, c.description, c.logged_by, a.name as asset_name 
        FROM changes c
        JOIN assets a ON c.asset_id = a.id
        WHERE c.asset_id = %s
        ORDER BY c.created_at DESC
        LIMIT %s
    """
    return execute_query(sql, (asset_id, limit), fetch=True) or []

    return execute_query(sql, (limit,), fetch=True) or []

# --- Helper Logic ---
def get_recursive_downstream(asset_id, edges=None):
    """
    Traverses the asset tree downwards to find all dependent assets.
    Uses recursion to find children, grandchildren, etc.
    
    Args:
        asset_id (int): The root asset ID for the search.
        edges (list): Accumulator list for graph edges.
        
    Returns:
        list: List of dicts [{'source': id, 'target': id, ...}, ...] representing dependencies.
    """
    if edges is None:
        edges = []
        
    children = execute_query("SELECT id, name, type FROM assets WHERE parent_id = %s", (asset_id,), fetch=True) or []
    
    for child in children:
        edges.append({'source': asset_id, 'target': child['id'], 'target_name': child['name'], 'target_type': child['type']})
        get_recursive_downstream(child['id'], edges)
        
    return edges

def build_tree(assets):
    """
    Converts a flat list of asset records into a nested tree structure.
    Also serves as the place to apply custom sorting specific to KPU's business logic.
    
    Args:
        assets (list): Flat list of asset dictionaries.
        
    Returns:
        list: Root nodes, each populated with a 'children' list.
    """
    nodes = {a['id']: {'data': a, 'children': []} for a in assets}
    tree = []
    
    for a in assets:
        pid = a['parent_id']
        node = nodes[a['id']]
        if pid is None:
            tree.append(node)
        elif pid in nodes:
            nodes[pid]['children'].append(node)
            
    # --- Custom Sort Priority (Business Logic) ---
    # Defines the visual order of asset types in the tree (e.g., Company at top)
    TYPE_SORT_ORDER = {
        "Company": 0,
        "Service": 1,
        "Offering": 2,
        "System": 3,
        "Sub-System": 4,
        "Group": 5,
        "Asset": 6,
        "Feature": 7,
        "Category": 99 # Categories pushed to bottom for cleaner grouping
    }
    
    def sort_key(node):
        start_rank = TYPE_SORT_ORDER.get(node['data']['type'], 50)
        return (start_rank, node['data']['name'])
        
    # Sort Root Level
    tree.sort(key=sort_key)
    
    # Sort Children Recursively
    for vid, v in nodes.items():
        if v['children']:
            v['children'].sort(key=sort_key)
            
    return tree

# --- CRUD Operations ---
def add_asset(name, parent_id, asset_type, description):
    """Inserts a new asset record."""
    sql = "INSERT INTO assets (name, parent_id, type, description) VALUES (%s, %s, %s, %s)"
    return execute_query(sql, (name, parent_id, asset_type, description))

def update_asset(asset_id, name, asset_type, description):
    """Updates an existing asset's details."""
    sql = "UPDATE assets SET name=%s, type=%s, description=%s WHERE id=%s"
    return execute_query(sql, (name, asset_type, description, asset_id))

def delete_asset(asset_id):
    """Deletes an asset. Database CASCADE rules will remove children automatically."""
    return execute_query("DELETE FROM assets WHERE id=%s", (asset_id,))

# --- ISO 27001 Operations ---
def fetch_all_controls():
    """Gets the master list of ISO 27001 controls."""
    return execute_query("SELECT * FROM iso_controls ORDER BY id", fetch=True) or []

def fetch_linked_controls(asset_id):
    """Gets ISO controls linked to a specific asset, including status/notes."""
    sql = """
        SELECT ic.*, ac.status, ac.notes, ac.linked_at 
        FROM iso_controls ic
        JOIN asset_controls ac ON ic.id = ac.control_id
        WHERE ac.asset_id = %s
    """
    return execute_query(sql, (asset_id,), fetch=True) or []

def link_asset_control(asset_id, control_id, status="Applicable", notes=""):
    """Links an ISO control to an asset (UPSERT operation)."""
    sql = """
        INSERT INTO asset_controls (asset_id, control_id, status, notes)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE status=%s, notes=%s
    """
    return execute_query(sql, (asset_id, control_id, status, notes, status, notes))

def unlink_asset_control(asset_id, control_id):
    """Removes a link between an asset and an ISO control."""
    return execute_query("DELETE FROM asset_controls WHERE asset_id=%s AND control_id=%s", (asset_id, control_id))

# --- NIST 2.0 Operations ---
def fetch_all_nist_controls():
    """Gets the master list of NIST CSF 2.0 controls."""
    return execute_query("SELECT * FROM nist_controls ORDER BY id", fetch=True) or []

def fetch_linked_nist_controls(asset_id):
    """Gets NIST controls linked to a specific asset."""
    sql = """
        SELECT nc.*, anc.status, anc.notes, anc.linked_at 
        FROM nist_controls nc
        JOIN asset_nist_controls anc ON nc.id = anc.control_id
        WHERE anc.asset_id = %s
    """
    return execute_query(sql, (asset_id,), fetch=True) or []

def link_asset_nist_control(asset_id, control_id, status="Applicable", notes=""):
    """Links a NIST control to an asset (UPSERT operation)."""
    sql = """
        INSERT INTO asset_nist_controls (asset_id, control_id, status, notes)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE status=%s, notes=%s
    """
    return execute_query(sql, (asset_id, control_id, status, notes, status, notes))

def unlink_asset_nist_control(asset_id, control_id):
    """Removes a link between an asset and a NIST control."""
    return execute_query("DELETE FROM asset_nist_controls WHERE asset_id=%s AND control_id=%s", (asset_id, control_id))

# --- Policy Operations ---
def add_policy(name, category, summary, content=None):
    """Creates a new organizational policy record."""
    sql = "INSERT INTO policies (name, category, summary, content) VALUES (%s, %s, %s, %s)"
    return execute_query(sql, (name, category, summary, content))

def update_policy(policy_id, name, category, summary, content):
    """Updates an existing policy."""
    sql = "UPDATE policies SET name=%s, category=%s, summary=%s, content=%s WHERE id=%s"
    return execute_query(sql, (name, category, summary, content, policy_id))

def delete_policy(policy_id):
    """Deletes a policy."""
    return execute_query("DELETE FROM policies WHERE id=%s", (policy_id,))

def get_all_policies():
    """Retrieves all policies ordered by category."""
    return execute_query("SELECT * FROM policies ORDER BY category, name", fetch=True) or []
    
def link_policy_nist(policy_id, nist_id):
    """Maps a Policy to a NIST control (Verification mechanism)."""
    sql = "INSERT IGNORE INTO policy_nist_mappings (policy_id, nist_control_id) VALUES (%s, %s)"
    return execute_query(sql, (policy_id, nist_id))

def unlink_policy_nist(policy_id, nist_id):
    """Removes a Policy-to-NIST mapping."""
    return execute_query("DELETE FROM policy_nist_mappings WHERE policy_id=%s AND nist_control_id=%s", (policy_id, nist_id))

def get_policy_nist_links(policy_id):
    """Gets all NIST controls associated with a specific policy."""
    sql = """SELECT nc.* FROM nist_controls nc
             JOIN policy_nist_mappings pm ON nc.id = pm.nist_control_id
             WHERE pm.policy_id = %s"""
    return execute_query(sql, (policy_id,), fetch=True) or []

# --- UI Components ---
# Mapping for Asset Types to Icons and Colors
STYLE_MAP = {
    "Company":    {"icon": "🏢", "color": "#1f77b4", "size": "1.2em"},
    "Category":   {"icon": "📂", "color": "#7f7f7f", "size": "1.1em"},
    "System":     {"icon": "🖥️", "color": "#2ca02c", "size": "1.1em"},
    "Sub-System": {"icon": "🧩", "color": "#98df8a", "size": "1.0em"},
    "Service":    {"icon": "⚙️", "color": "#d62728", "size": "1.1em"},
    "Offering":   {"icon": "🎁", "color": "#9467bd", "size": "1.0em"},
    "Feature":    {"icon": "✨", "color": "#e377c2", "size": "1.0em"},
    "Asset":      {"icon": "📦", "color": "#ff7f0e", "size": "1.0em"},
    "Group":      {"icon": "👥", "color": "#8c564b", "size": "1.0em"},
    "Facility":   {"icon": "🏭", "color": "#bcbd22", "size": "1.1em"}
}

def render_tree_node(node, level=0, manage_mode=False):
    """
    Recursive function to render the asset tree in the Streamlit UI.
    
    Args:
        node (dict): The current tree node ({data:..., children:[...]}).
        level (int): Indentation level (recursion depth).
        manage_mode (bool): If True, shows Edit/Delete controls instead of Log controls.
    """
    data = node['data']
    children = node['children']
    
    atype = data['type']
    style = STYLE_MAP.get(atype, {"icon": "🔹", "color": "#333", "size": "1.0em"})
    
    # Construct Label
    label = f"{style['icon']} {data['name']}  [{atype}]"
    if data['description']:
        desc = (data['description'][:60] + '..') if len(data['description']) > 60 else data['description']
        label += f" — {desc}"
    
    # Visual Layout
    container = st.container()
    
    # Custom Indentation for visual clarity on Infrastructure assets
    if data['name'] == "KPU Infrastructure Assets":
        _, col = st.columns([0.3, 10]) 
        target_container = col
    else:
        target_container = container
    
    if children:
        # Render Parent Node as Expander
        with target_container.expander(label, expanded=level < 2): 
            # Show buttons at the top of the expanded area if Root or Management Mode
            if level > 0 or manage_mode:
                _render_node_actions(data, manage_mode)
            # Recurse for children
            for child in children:
                render_tree_node(child, level + 1, manage_mode)
    else:
        # Render Leaf Node as a flat Row
        with container:
            cols = st.columns([0.5, 4.0, 2.0])
            
            # HTML Styling for attractive leaf display
            html_label = f"""
            <div style='margin-left: 5px; padding: 2px;'>
                <span style='font-size:{style['size']}; margin-right: 5px;'>{style['icon']}</span>
                <span style='font-weight:600; font-size:1.05em; color:{style['color']}'>{data['name']}</span>
                <span style='background-color:#f0f2f6; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-left:8px; color:#555;'>{atype}</span>
            </div>
            """
            
            cols[1].markdown(html_label, unsafe_allow_html=True)
            with cols[2]:
                _render_node_actions(data, manage_mode, is_leaf=True)

def _render_node_actions(data, manage_mode, is_leaf=False):
    """
    Renders context-aware buttons (Edit, Logs, Compliance) for a node.
    """
    if manage_mode:
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
        # Add Child Button
        if c1.button("➕", key=f"add_{data['id']}", help="Add Child"):
            st.session_state.mgmt_target = data
            st.session_state.mgmt_action = "add"
            st.rerun()
        # Edit Button
        if c2.button("✏️", key=f"edit_{data['id']}", help="Edit"):
            st.session_state.mgmt_target = data
            st.session_state.mgmt_action = "edit"
            st.rerun()
        # Delete Button (Dangerous)
        if c3.button("🗑️", key=f"del_{data['id']}", help="Delete"):
            if delete_asset(data['id']):
                st.success("Deleted!")
                st.rerun()
        # Compliance Shield Button
        if c4.button("🛡️", key=f"iso_{data['id']}", help="Manage Compliance (ISO/NIST)"):
            st.session_state.mgmt_target = data
            st.session_state.mgmt_action = "compliance"
            st.rerun()
        # Grid Button (Navigate to Grid View)
        if data['type'] in ["Category", "Group", "Service", "System", "Company"]:
             with c5:
                 st.link_button("⊞", f"/Grid_Editor?id={data['id']}", help="Grid Editor (New Tab)")

    else:
        # Viewer/Log Mode
        # Show Active Ticket Count
        count = data.get('active_tickets', 0)
        
        # Dynamic styling for assets with active tickets
        if count > 0:
            btn_label = f"🎫 Ticket ({count})"
            btn_type = "primary" # Highlights active assets
            btn_help = f"{count} active tickets."
        else:
            btn_label = "🎫 Ticket"
            btn_type = "secondary"
            btn_help = "Create a Service Request or Incident."

        b1, b2 = st.columns([1, 2])
        
        with b1:
             # Link to History Page
             if count > 0:
                st.link_button("📜", f"/History?id={data['id']}", help="View Ticket History")
        
        with b2:
            # Open Log Modal
            if st.button(btn_label, key=f"btn_{data['id']}", type=btn_type, help=btn_help):
                 st.session_state.selected_asset = data
                 st.session_state.show_ticket_form = True
                 st.rerun()

# --- Main App Execution ---

# 1. Sidebar Setup
try:
    st.sidebar.image("logo.png", use_container_width=True)
except:
    st.sidebar.header("KPU Tel")

st.title("2D Mandrake v2.0 🔧")

# Navigation Menu
page = st.sidebar.radio("Navigation", ["Hierarchy Explorer", "Policies & Standards", "Analysis & Impact", "Recent Changes"])

# ⚠️ PAGE: HIERARCHY EXPLORER
if page == "Hierarchy Explorer":
    col_header, col_toggle = st.columns([3, 1])
    col_header.subheader("Asset & Service Hierarchy")
    col_header.caption("🔗 Connected Table: `assets`")
    
    # Management Mode Toggle (Admin swich)
    manage_mode = col_toggle.toggle("🛠️ Manage Mode", key="mgmt_mode_toggle")
    
    # Fetch and Build Tree
    assets_flat = fetch_hierarchy()
    tree_root = build_tree(assets_flat)
    
    # --- MODALS (Forms) ---
    
    # A. Ticket Form (Visible in View Mode)
    if st.session_state.get("show_ticket_form", False) and not manage_mode:
        asset = st.session_state.selected_asset
        with st.form("ticket_form"):
            st.subheader(f"Create Ticket for: {asset['name']}")
            st.caption("🔗 Connected Table: `tickets`")
            
            c1, c2 = st.columns(2)
            t_type = c1.selectbox("Type", ["Incident", "Service Request", "Change", "Problem"])
            t_prio = c2.select_slider("Priority", ["Low", "Medium", "High", "Critical"])
            
            t_title = st.text_input("Title (Short Summary)")
            t_desc = st.text_area("Detailed Description")
            
            # File Upload
            t_files = st.file_uploader("Attach Documents", accept_multiple_files=True, help="Stored in 2D_Storage/")
            
            c3, c4 = st.columns(2)
            t_status = c3.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
            t_user = c4.text_input("Logged By", value="Admin")
            
            if st.form_submit_button("Submit Ticket"):
                success, res_or_err = create_ticket(asset['id'], t_type, t_title, t_desc, t_prio, t_status, t_user)
                if success:
                    ticket_id = res_or_err
                    # Handle Uploads
                    if t_files:
                        for f in t_files:
                            save_attachment(ticket_id, f)
                            
                    save_mode = st.session_state.db_manager.mode
                    mode_icon = "☁️ Cloud" if save_mode == "CLOUD" else "📂 Local"
                    
                    st.success(f"Ticket Created & Files Uploaded! (Saved to {mode_icon})")
                    st.session_state.show_ticket_form = False
                    st.rerun()
                else:
                    st.error(f"Error: {res_or_err}")
        st.divider()

    # B. Management Forms (Visible in Manage Mode)
    if manage_mode and "mgmt_action" in st.session_state:
        action = st.session_state.mgmt_action
        target = st.session_state.mgmt_target
        
        # B1. Compliance Management (ISO/NIST)
        if action in ["compliance", "iso"]:
            with st.container():
                c_head, c_close = st.columns([5, 1])
                c_head.subheader(f"🛡️ Compliance: {target['name']}")
                if c_close.button("✖️ Close"):
                    del st.session_state.mgmt_action
                    st.rerun()
                    
            st.caption("Manage ISO 27001 and NIST 2.0 Controls")
            
            # Compliance Tabs
            tab_iso, tab_nist = st.tabs(["ISO 27001", "NIST 2.0"])
            
            # ISO Tab
            with tab_iso:
                with st.form("iso_mgmt_form"):
                    st.caption("🔗 Table: `iso_controls`")
                    linked = fetch_linked_controls(target['id'])
                    
                    if linked:
                        st.write("**Current ISO Controls:**")
                        for l in linked:
                            st.markdown(f"- **{l['id']}**: {l['description']} *({l['status']})*")
                    else:
                        st.info("No ISO controls linked.")
                    
                    st.markdown("---")
                    st.write("**Link New ISO Control**")
                    
                    all_controls = fetch_all_controls()
                    control_opts = [f"{c['id']} - {c['description'][:60]}..." for c in all_controls]
                    
                    c_idx = st.selectbox("Select ISO Control", range(len(control_opts)), format_func=lambda x: control_opts[x])
                    c_status = st.selectbox("Status", ["Applicable", "Not Applicable", "Compliant", "Non-Compliant"], key="iso_stat")
                    c_notes = st.text_area("Notes", key="iso_note")
                    
                    if st.form_submit_button("Link ISO Control"):
                        sel_id = all_controls[c_idx]['id']
                        if link_asset_control(target['id'], sel_id, c_status, c_notes):
                            st.success(f"Linked {sel_id}")
                            st.rerun()

            # NIST Tab
            with tab_nist:
                with st.form("nist_mgmt_form"):
                    st.caption("🔗 Table: `nist_controls`")
                    linked_nist = fetch_linked_nist_controls(target['id'])
                    
                    if linked_nist:
                        st.write("**Current NIST Controls:**")
                        for l in linked_nist:
                            st.markdown(f"- **{l['id']}**: {l['description']} *({l['status']})*")
                    else:
                        st.info("No NIST controls linked.")
                    
                    st.markdown("---")
                    st.write("**Link New NIST Control**")
                    
                    all_nist = fetch_all_nist_controls()
                    nist_opts = [f"{c['id']} ({c['function']}) - {c['description'][:50]}..." for c in all_nist]
                    
                    n_idx = st.selectbox("Select NIST Control", range(len(nist_opts)), format_func=lambda x: nist_opts[x])
                    n_status = st.selectbox("Status", ["Applicable", "Not Applicable", "Compliant", "Non-Compliant"], key="nist_stat")
                    n_notes = st.text_area("Notes", key="nist_note")
                    
                    if st.form_submit_button("Link NIST Control"):
                        sel_id = all_nist[n_idx]['id']
                        if link_asset_nist_control(target['id'], sel_id, n_status, n_notes):
                            st.success(f"Linked {sel_id}")
                            st.rerun()
                        
        # B2. Add/Edit Asset Forms
        elif action in ["add", "edit"]:
            with st.form("mgmt_form"):
                st.info(f"Action: {action.upper()} on {target['name']}")
                st.caption("🔗 Connected Table: `assets`")
                
                new_name = st.text_input("Name", value=target['name'] if action == 'edit' else "")
                new_type = st.selectbox("Type", ["Company", "Category", "System", "Sub-System", "Service", "Offering", "Feature", "Asset", "Group", "Facility"], index=0)
                new_desc = st.text_area("Description", value=target.get('description', '') if action == 'edit' else "")
                
                if st.form_submit_button("Save"):
                    if action == "add":
                        if add_asset(new_name, target['id'], new_type, new_desc):
                            st.success("Added!")
                            del st.session_state.mgmt_action
                            st.rerun()
                    elif action == "edit":
                        if update_asset(target['id'], new_name, new_type, new_desc):
                            st.success("Updated!")
                            del st.session_state.mgmt_action
                            st.rerun()
        st.divider()

    # Finally, Render the Main Tree
    for root_node in tree_root:
        render_tree_node(root_node, manage_mode=manage_mode)

# ⚠️ PAGE: IMPACT ANALYSIS
elif page == "Analysis & Impact":
    st.subheader("Dependency & Impact Visualizer")
    st.caption("🔗 Connected Table: `assets` (Recursive Relationship)")
    st.info("Select a core asset to visualize downstream dependencies.")
    
    assets = fetch_hierarchy()
    asset_map = {a['name']: a['id'] for a in assets}
    
    selected_asset_name = st.selectbox("Select Asset", options=list(asset_map.keys()))
    
    if selected_asset_name:
        root_id = asset_map[selected_asset_name]
        
        if st.button("Generate Impact Map"):
            with st.spinner("Tracing dependencies..."):
                edges = get_recursive_downstream(root_id)
                
                if not edges:
                    st.warning("No downstream dependencies found for this asset.")
                else:
                    # Use Graphviz to draw diagram
                    graph = graphviz.Digraph()
                    graph.attr(rankdir='TB')
                    
                    # Root Node styling
                    graph.node(str(root_id), selected_asset_name, shape='box', style='filled', color='lightblue')
                    
                    for edge in edges:
                        # Color coding for readability
                        fill = 'white'
                        if edge['target_type'] == 'Group': fill = 'lightgrey'
                        if edge['target_type'] == 'Asset': fill = 'lightyellow'
                        
                        graph.node(str(edge['target']), edge['target_name'], style='filled', fillcolor=fill)
                        graph.edge(str(edge['source']), str(edge['target']))
                    
                    st.graphviz_chart(graph)
                    st.caption(f"Found {len(edges)} downstream dependencies.")

# ⚠️ PAGE: POLICIES
elif page == "Policies & Standards":
    st.title("📜 Policy & Standards Library")
    st.caption("🔗 Connected Table: `policies` JOIN `nist_controls`")
    
    # 1. Create Policy Form
    with st.expander("➕ Create New Policy"):
        with st.form("new_policy_form"):
            pn = st.text_input("Policy Name")
            pc = st.selectbox("Category", ["Identify", "Protect", "Detect", "Respond", "Recover", "Governance", "General"])
            ps = st.text_area("Summary (from RTF/Doc)")
            p_content = st.text_area("Full Content (Optional)")
            
            if st.form_submit_button("Create Policy"):
                if add_policy(pn, pc, ps, p_content):
                    st.success(f"Created policy: {pn}")
                    st.rerun()
                else:
                    st.error("Failed to create policy.")
    
    st.divider()
    
    # 2. List & Manage Policies
    policies = get_all_policies()
    
    if not policies:
        st.info("No policies defined yet.")
    else:
        # Group display by Category for readability
        df_p = pd.DataFrame(policies)
        cats = df_p['category'].unique()
        
        for cat in cats:
            st.markdown(f"### {cat}")
            cat_policies = df_p[df_p['category'] == cat]
            
            for _, p in cat_policies.iterrows():
                # Individual Policy Card
                with st.expander(f"📄 {p['name']}", expanded=False):
                    c1, c2 = st.columns([3, 2])
                    
                    with c1:
                        st.markdown(f"**Summary:** {p['summary']}")
                        if p['content']:
                            st.info(p['content'])
                            
                        if st.button("Delete Policy", key=f"del_pol_{p['id']}"):
                            if delete_policy(p['id']):
                                st.rerun()
                                
                    with c2:
                        st.markdown("**Mapped NIST Controls**")
                        # Display Mapped Controls
                        links = get_policy_nist_links(p['id'])
                        if links:
                            for l in links:
                                c_lbl = f"{l['id']} ({l['function']})"
                                col_a, col_b = st.columns([4, 1])
                                col_a.caption(f"{c_lbl}: {l['description'][:40]}...")
                                if col_b.button("❌", key=f"ul_{p['id']}_{l['id']}"):
                                    unlink_policy_nist(p['id'], l['id'])
                                    st.rerun()
                        else:
                            st.caption("No controls mapped.")
                        
                        st.divider()
                        
                        # Link Control Form
                        all_nist = fetch_all_nist_controls()
                        nist_opts = [f"{c['id']} - {c['description'][:30]}..." for c in all_nist]
                        
                        sel_idx = st.selectbox("Link Control", range(len(nist_opts)), format_func=lambda x: nist_opts[x], key=f"lnk_sel_{p['id']}")
                        
                        if st.button("Link", key=f"lnk_btn_{p['id']}"):
                            sel_id = all_nist[sel_idx]['id']
                            if link_policy_nist(p['id'], sel_id):
                                st.success("Linked!")
                                st.rerun()

# --- Footer ---
st.sidebar.markdown("---")
col1, col2, col3 = st.sidebar.columns([1, 2, 1])
with col2:
    try:
        st.image("dubay_logo.png", use_container_width=True)
    except:
        st.caption("Powered by Dubay.Tech")

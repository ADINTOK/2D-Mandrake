import streamlit as st
import importlib
import database_manager
importlib.reload(database_manager)
from database_manager import DatabaseManager
import pandas as pd
import datetime
import getpass

st.set_page_config(page_title="2D Mandrake - Service Management & Compliance", page_icon="🌳", layout="wide")

st.title("➕ Create New Ticket")
st.caption("Log a new incident or request and associate it with multiple affected assets.")

# Initialize Database Manager
# Checks for VERSION_ID to ensure we pick up class updates in the streamlit session
if 'db_manager' not in st.session_state or \
   not hasattr(st.session_state.db_manager, 'VERSION_ID') or \
   st.session_state.db_manager.VERSION_ID != DatabaseManager.VERSION_ID:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager

# Render Global Sidebar (Branding + Connectivity Status)
db.render_sidebar_status()

# Success Confirmation (Standardized)
if st.session_state.get('success_ticket_id'):
    st.success(f"✅ Ticket #{st.session_state.success_ticket_id} Created Successfully!")
    if st.button("Dismiss"):
        st.session_state.success_ticket_id = None
        st.rerun()

# --- Fetch Assets for Multi-Select ---
assets_machines = db.execute("SELECT id, name FROM kpu_enterprise_computing_machines", fetch=True)
assets_software = db.execute("SELECT id, name FROM kpu_enterprise_software", fetch=True)

# Process for SelectBox options
machine_options = {f"💻 {m['name']} (ID: {m['id']})": {'id': m['id'], 'type': 'computing_machine'} for m in assets_machines} if assets_machines else {}
software_options = {f"💾 {s['name']} (ID: {s['id']})": {'id': s['id'], 'type': 'software'} for s in assets_software} if assets_software else {}

all_options = {**machine_options, **software_options}

# --- Form ---

with st.form("create_ticket_form"):
    c1, c2 = st.columns([0.7, 0.3])
    
    with c1:
        title = st.text_input("Title", placeholder="e.g., Unable to access VPN")
        desc = st.text_area("Description", placeholder="Detailed explanation of the issue...", height=150)
        
        st.markdown("### Related Assets")
        selected_labels = st.multiselect("Select Affected Assets", options=all_options.keys(), placeholder="Search for machines or software...")
        
    with c2:
        priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
        
        # SLA Hint
        sla_map = {"Critical": "4 Hours", "High": "8 Hours", "Medium": "24 Hours", "Low": "3 Days"}
        st.caption(f"⚡ SLA Target: **{sla_map.get(priority, 'N/A')}** response time.")
        
        status = st.selectbox("Status", ["Open", "In Progress", "Pending", "Resolved", "Closed"])
        assignee = st.text_input("Assign To", value="Unassigned")
        logged_by_default = getpass.getuser()
        logged_by = st.text_input("Logged By", value=logged_by_default)
        due_date = st.date_input("Due Date (Manual Override)", value=datetime.date.today() + datetime.timedelta(days=3))
        
    submitted = st.form_submit_button("Submit Ticket", type="primary")
    
    if submitted:
        if not title:
            st.error("Title is required.")
        else:
            # Prepare Asset List
            asset_list = [all_options[label] for label in selected_labels]
            
            with st.spinner("Creating Ticket..."):
                success, res = db.create_ticket_with_assets(
                    title=title,
                    description=desc,
                    priority=priority,
                    status=status,
                    assigned_to=assignee,
                    due_date=due_date,
                    asset_list=asset_list,
                    logged_by=logged_by
                )
                
                if success:
                    st.session_state.success_ticket_id = res
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"Failed to create ticket: {res}")


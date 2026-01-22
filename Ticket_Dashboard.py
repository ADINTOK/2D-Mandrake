import streamlit as st
import importlib
import database_manager
importlib.reload(database_manager)
from database_manager import DatabaseManager
import pandas as pd

# =============================================================================
# Page: Ticket Dashboard
# =============================================================================
# Provides a high-level overview of all tickets in the system.
# Key Features:
# - KPI Metrics (Total Open, Critical Issues).
# - Visualization (Charts by Status and Type).
# - Filterable Data Table for global ticket management.
# =============================================================================

st.set_page_config(page_title="2D Mandrake - Service Management & Compliance", page_icon="🌳", layout="wide")

# Initialize DB Manager
if 'db_manager' not in st.session_state or \
   not hasattr(st.session_state.db_manager, 'VERSION_ID') or \
   st.session_state.db_manager.VERSION_ID != DatabaseManager.VERSION_ID:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager

# Ensure Sidebar Connectivity Status is visible (Sync Buttons)
db.render_sidebar_status()

# Layout: Title + Action Button
h_col1, h_col2 = st.columns([0.8, 0.2])
with h_col1:
    st.title("📊 Ticket Dashboard")
with h_col2:
    st.write("") # Spacer
    st.write("")
    st.page_link("pages/01_Create_Ticket.py", label="➕ Create New Ticket", icon="🎫", help="Open Ticket Creation Form")

st.info("""
**ITSM Operational Oversight**
Unified visibility into the enterprise service desk. 
Track incident velocity, identify recurring systemic problems, and manage the Change Advisory Board (CAB) workflow. 
This dashboard correlates tickets with specific assets from the hierarchy, ensuring full accountability 
and SLA adherence across the business landscape.
""")

def execute_query(query, params=None, fetch=False):
    """Executes a query using the global DB manager."""
    return st.session_state.db_manager.execute(query, params, fetch)

# --- Fetch Data ---
# We fetch all tickets to calculate metrics locally
sql = """
    SELECT t.*, 
           COALESCE(a.name, s.name, c.name, 'Unknown') as asset_name
    FROM tickets t
    LEFT JOIN assets a ON t.asset_id = a.id AND (t.related_type = 'asset' OR t.related_type IS NULL)
    LEFT JOIN kpu_enterprise_software s ON t.asset_id = s.id AND t.related_type = 'software'
    LEFT JOIN kpu_enterprise_computing_machines c ON t.asset_id = c.id AND t.related_type = 'computing_machine'
    ORDER BY t.created_at DESC
"""
tickets = execute_query(sql, fetch=True)

if not tickets:
    st.info("No tickets found in the system.")
    st.stop()

df = pd.DataFrame(tickets)

# --- KPI Metrics ---
# Active = Not Closed
active_df = df[df['status'] != 'Closed']
critical_df = active_df[active_df['priority'] == 'Critical']

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Tickets", len(df), help="Grand total of all recorded tickets since system inception.")
col2.metric("Active Tickets", len(active_df), help="Tickets currently in Open or In Progress state.")
col3.metric("Critical Issues", len(critical_df), help="High-impact incidents requiring immediate response.", delta_color="inverse")
col4.metric("Recently Closed", len(df[df['status'] == 'Closed']), help="Tickets successfully resolved and closed.")

st.divider()

# --- Tabs for ITIL Modules ---
tab_metrics, tab_problems, tab_cab = st.tabs(["📊 Metrics & List", "🚧 Problem Management", "👨‍⚖️ CAB Workbench"])

with tab_metrics:
    # --- Visualizations ---
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Tickets by Status")
        status_counts = df['status'].value_counts()
        st.bar_chart(status_counts)

    with c2:
        st.subheader("Tickets by Type")
        type_counts = df['ticket_type'].value_counts()
        st.bar_chart(type_counts)

    # --- Detailed Table with SLA ---
    st.subheader("Global Ticket List")

    # Filters
    f1, f2 = st.columns(2)
    with f1:
        available_statuses = df['status'].unique()
        default_statuses = [s for s in ["Open", "In Progress"] if s in available_statuses]
        f_status = st.multiselect("Filter by Status", options=available_statuses, default=default_statuses)
    with f2:
        f_type = st.multiselect("Filter by Type", options=df['ticket_type'].unique(), default=df['ticket_type'].unique())

    # Apply Filters
    filtered_df = df[df['status'].isin(f_status) & df['ticket_type'].isin(f_type)]

    # SLA Calc: Check for breaches (Mock 'now' for python or use pd.to_datetime)
    if 'due_date' in filtered_df.columns:
        filtered_df['due_date'] = pd.to_datetime(filtered_df['due_date'], format='mixed', errors='coerce')
        now = pd.Timestamp.now()
        # Highlight Logic: If Open and Now > Due Date
        def highlight_breach(row):
            if row['status'] not in ['Closed', 'Resolved'] and row['due_date'] < now:
                return 'background-color: #ffcccc' # Red tint
            return ''
        # Pandas Styler not fully supported in st.dataframe editable, but we can add a 'Breached' column
        filtered_df['SLA Breached'] = (filtered_df['status'].isin(['Open', 'In Progress'])) & (filtered_df['due_date'] < now)

    st.dataframe(
        filtered_df,
        column_order=["id", "SLA Breached", "created_at", "due_date", "status", "priority", "ticket_type", "asset_name", "title"],
        column_config={
            "id": st.column_config.NumberColumn("ID", format="#%d"),
            "created_at": st.column_config.DatetimeColumn("Created", format="D MMM, h:mm a"),
            "due_date": st.column_config.DatetimeColumn("Due By", format="D MMM, h:mm a"),
            "asset_name": "Asset",
            "SLA Breached": st.column_config.CheckboxColumn("⚠️ User Breach?", disabled=True)
        },
        use_container_width=True,
        hide_index=True
    )

with tab_problems:
    st.header("Problem Management")
    st.caption("Identify Root Causes (RCA) and link Incidents.")
    
    # 1. Create Problem
    with st.expander("🧩 Create New Problem Record"):
        with st.form("new_problem_form"):
            p_title = st.text_input("Problem Statement")
            p_desc = st.text_area("Description")
            p_rca = st.text_area("Root Cause Analysis (RCA)")
            if st.form_submit_button("Create Problem"):
                if db.mode == "CLOUD":
                    db.execute("INSERT INTO problems (title, description, root_cause_analysis, created_at) VALUES (%s, %s, %s, NOW())", (p_title, p_desc, p_rca))
                else:
                    db.execute("INSERT INTO problems (title, description, root_cause_analysis, created_at) VALUES (?, ?, ?, datetime('now'))", (p_title, p_desc, p_rca))
                st.success("Problem Record Created!")
                st.rerun()

    # 2. List Problems
    probs = execute_query("SELECT * FROM problems ORDER BY created_at DESC", fetch=True)
    if probs:
        p_df = pd.DataFrame(probs)
        st.dataframe(p_df, use_container_width=True)
    else:
        st.info("No Active Problems.")

with tab_cab:
    st.header("Change Advisory Board (CAB)")
    st.caption("Review and Approve RFCs (Request for Change).")
    
    # Filter for Changes
    changes = df[df['ticket_type'] == 'Change']
    
    if not changes.empty:
        for idx, row in changes.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                with c1:
                    st.markdown(f"**#{row['id']} {row['title']}**")
                    st.caption(f"Priority: {row['priority']} | Status: {row['status']}")
                with c2:
                     if st.button("✅ Approve", key=f"app_{row['id']}"):
                         db.execute(f"UPDATE tickets SET status='Approved' WHERE id={row['id']}")
                         st.toast(f"Change #{row['id']} Approved!")
                         st.rerun()
                with c3:
                     if st.button("❌ Reject", key=f"rej_{row['id']}"):
                         db.execute(f"UPDATE tickets SET status='Rejected' WHERE id={row['id']}")
                         st.toast(f"Change #{row['id']} Rejected!")
                         st.rerun()
    else:
        st.success("🎉 No Pending Changes for Review.")

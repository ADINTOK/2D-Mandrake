import streamlit as st
import pandas as pd
from database_manager import DatabaseManager

# =============================================================================
# Page: Ticket Dashboard
# =============================================================================
# Provides a high-level overview of all tickets in the system.
# Key Features:
# - KPI Metrics (Total Open, Critical Issues).
# - Visualization (Charts by Status and Type).
# - Filterable Data Table for global ticket management.
# =============================================================================

st.set_page_config(page_title="Ticket Dashboard", page_icon="📊", layout="wide")

st.title("📊 Ticket Dashboard")

# Initialize DB Manager
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

def execute_query(query, params=None, fetch=False):
    """Executes a query using the global DB manager."""
    return st.session_state.db_manager.execute(query, params, fetch)

# --- Fetch Data ---
# We fetch all tickets to calculate metrics locally
sql = """
    SELECT t.id, t.created_at, t.ticket_type, t.priority, t.status, t.title, t.logged_by, a.name as asset_name 
    FROM tickets t
    JOIN assets a ON t.asset_id = a.id
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
col1.metric("Total Tickets", len(df))
col2.metric("Active Tickets", len(active_df))
col3.metric("Critical Issues", len(critical_df))
col4.metric("Recently Closed", len(df[df['status'] == 'Closed']))

st.divider()

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

# --- Detailed Table ---
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

st.dataframe(
    filtered_df,
    column_order=["id", "created_at", "status", "priority", "ticket_type", "asset_name", "title", "logged_by"],
    column_config={
        "id": st.column_config.NumberColumn("ID", format="#%d"),
        "created_at": st.column_config.DatetimeColumn("Created", format="D MMM, h:mm a"),
        "asset_name": "Asset",
    },
    use_container_width=True,
    hide_index=True
)

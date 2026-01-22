
import streamlit as st
import pandas as pd
from database_manager import DatabaseManager
import time
import getpass

st.set_page_config(layout="wide", page_title="Enterprise Computing Machines", page_icon="🖥️")

st.title("🖥️ Enterprise Computing Machines")
st.info("""
**Endpoint Visibility & Infrastructure Health**
Comprehensive inventory of workstations, servers, and appliances (SafeList Devices). 
Maintain tactical oversight of the physical and virtual computing fleet by tracking IP/MAC addresses, 
owner assignments, and operating system distributions. This registry serves as the baseline 
for security audits and hardware lifecycle management.
""")

# Initialize Database Manager
if 'db_manager' not in st.session_state or \
   not hasattr(st.session_state.db_manager, 'VERSION_ID') or \
   st.session_state.db_manager.VERSION_ID != DatabaseManager.VERSION_ID:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager
db.render_sidebar_status()

# Success Confirmation
if st.session_state.get('success_ticket_id'):
    st.success(f"✅ Ticket #{st.session_state.success_ticket_id} Created Successfully!")
    if st.button("Dismiss"):
        st.session_state.success_ticket_id = None
        st.rerun()

# --- STATE MANAGEMENT ---
if 'ecm_manage_mode' not in st.session_state:
    st.session_state.ecm_manage_mode = False

if 'ecm_edit_target' not in st.session_state:
    st.session_state.ecm_edit_target = None 

if 'ecm_ticket_target' not in st.session_state:
    st.session_state.ecm_ticket_target = None 

if 'ecm_comp_target' not in st.session_state:
    st.session_state.ecm_comp_target = None

# --- HELPERS ---
def fetch_machines():
    return db.execute("SELECT * FROM kpu_enterprise_computing_machines ORDER BY name", fetch=True) or []

def add_machine(asset_id, name, ip, mac, owner, os, loc):
    if db.mode == "CLOUD":
        sql = "INSERT INTO kpu_enterprise_computing_machines (asset_id, name, ip_address, mac_address, owner, os_type, location) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        return db.execute(sql, (asset_id, name, ip, mac, owner, os, loc))
    else:
        sql = "INSERT INTO kpu_enterprise_computing_machines (asset_id, name, ip_address, mac_address, owner, os_type, location) VALUES (?, ?, ?, ?, ?, ?, ?)"
        return db.execute(sql, (asset_id, name, ip, mac, owner, os, loc))

def update_machine(mid, asset_id, name, ip, mac, owner, os, loc):
    if db.mode == "CLOUD":
        sql = "UPDATE kpu_enterprise_computing_machines SET asset_id=%s, name=%s, ip_address=%s, mac_address=%s, owner=%s, os_type=%s, location=%s WHERE id=%s"
        return db.execute(sql, (asset_id, name, ip, mac, owner, os, loc, mid))
    else:
        sql = "UPDATE kpu_enterprise_computing_machines SET asset_id=?, name=?, ip_address=?, mac_address=?, owner=?, os_type=?, location=? WHERE id=?"
        return db.execute(sql, (asset_id, name, ip, mac, owner, os, loc, mid))

def delete_machine(mid):
    return db.execute("DELETE FROM kpu_enterprise_computing_machines WHERE id=%s", (mid,))

def create_machine_ticket(mid, t_type, title, desc, prio, status, user):
    return db.create_ticket(mid, t_type, title, desc, prio, user, related_type='computing_machine', status=status)

# --- COMPLIANCE HELPERS ---
def fetch_linked_controls(item_id):
    sql = "SELECT ic.*, ac.status FROM iso_controls ic JOIN asset_controls ac ON ic.id = ac.control_id WHERE ac.asset_id=%s AND ac.related_type='computing_machine'"
    if db.mode != "CLOUD": sql = sql.replace("%s", "?")
    return db.execute(sql, (item_id,), fetch=True) or []

def link_control(item_id, cid, stat, note):
    if db.mode == "CLOUD":
        sql = "INSERT INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (%s, 'computing_machine', %s, %s, %s)"
        check = db.execute("SELECT id FROM asset_controls WHERE asset_id=%s AND related_type='computing_machine' AND control_id=%s", (item_id, cid), fetch=True)
        if check:
            sql_up = "UPDATE asset_controls SET status=%s, notes=%s WHERE id=%s"
            return db.execute(sql_up, (stat, note, check[0]['id']))
        else:
            return db.execute(sql, (item_id, cid, stat, note))
    else:
        sql = "INSERT OR REPLACE INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (?, 'computing_machine', ?, ?, ?)"
        return db.execute(sql, (item_id, cid, stat, note))

def fetch_all_iso():
    return db.execute("SELECT * FROM iso_controls ORDER BY id", fetch=True) or []

# --- SIDEBAR TOGGLES ---
col_head, col_tog = st.columns([0.8, 0.2])
with col_tog:
    manage_mode = st.toggle("🛠️ Manage Mode", key="ecm_manage_mode", help="Enable administrative controls to provision or decommission computing assets.")

# --- MANAGE MODE: ADD/EDIT FORM ---
if manage_mode:
    with st.expander("➕ Add / ✏️ Edit Machine", expanded=(st.session_state.ecm_edit_target is not None or manage_mode)):
        is_edit = st.session_state.ecm_edit_target is not None
        target = st.session_state.ecm_edit_target if is_edit else {}
        
        st.caption("Enter machine details below.")
        with st.form("machine_mgmt_form"):
            c1, c2, c3 = st.columns(3)
            f_name = c1.text_input("Machine Name", value=target.get('name', ''))
            f_asset_id = c2.text_input("Asset ID", value=target.get('asset_id', ''))
            f_owner = c3.text_input("Owner", value=target.get('owner', ''))
            
            c4, c5, c6 = st.columns(3)
            f_ip = c4.text_input("IP Address", value=target.get('ip_address', ''))
            f_mac = c5.text_input("MAC Address", value=target.get('mac_address', ''))
            f_os = c6.text_input("OS Type", value=target.get('os_type', ''))
            
            f_loc = st.text_input("Location", value=target.get('location', ''))
            
            submitted = st.form_submit_button("Update Machine" if is_edit else "Add Machine")
            
            if submitted:
                if is_edit:
                    if update_machine(target['id'], f_asset_id, f_name, f_ip, f_mac, f_owner, f_os, f_loc):
                        st.success("Updated!")
                        st.session_state.ecm_edit_target = None
                        st.rerun()
                    else:
                        st.error("Update Failed.")
                else:
                    if add_machine(f_asset_id, f_name, f_ip, f_mac, f_owner, f_os, f_loc):
                        st.success("Added!")
                        st.rerun()
                    else:
                        st.error("Add Failed.")
        
        if is_edit:
             if st.button("Cancel Edit"):
                 st.session_state.ecm_edit_target = None
                 st.rerun()
    st.divider()

# --- TICKET CREATION MODAL ---
if st.session_state.ecm_ticket_target:
    tgt = st.session_state.ecm_ticket_target
    with st.form("machine_ticket_form"):
        st.subheader(f"🎫 New Ticket: {tgt['name']}")
        c1, c2 = st.columns(2)
        t_type = c1.selectbox("Type", ["Incident", "Service Request", "Change", "Problem"])
        t_prio = c2.select_slider("Priority", ["Low", "Medium", "High", "Critical"])
        
        t_title = st.text_input("Title")
        t_desc = st.text_area("Description")
        
        c3, c4 = st.columns(2)
        t_status = c3.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
        t_user = c4.text_input("Logged By", value=getpass.getuser())
        
        t_file = st.file_uploader("Attach Document/Image", type=["png", "jpg", "jpeg", "pdf", "docx", "txt"])
        
        if st.form_submit_button("Create Ticket"):
            new_id = create_machine_ticket(tgt['id'], t_type, t_title, t_desc, t_prio, t_status, t_user)
            if new_id:
                if t_file:
                    db.save_attachment(new_id, t_file)
                st.session_state.success_ticket_id = new_id
                st.session_state.ecm_ticket_target = None
                st.rerun()
            else:
                st.error("Failed to create ticket.")
                
    if st.button("Cancel Ticket"):
        st.session_state.ecm_ticket_target = None
        st.rerun()
    st.divider()

# --- COMPLIANCE MODAL ---
if st.session_state.ecm_comp_target:
    tgt = st.session_state.ecm_comp_target
    st.subheader(f"🛡️ Compliance: {tgt['name']}")
    if st.button("Close Compliance"):
        st.session_state.ecm_comp_target = None
        st.rerun()

    with st.form("iso_comp_form_m"):
        st.caption("ISO 27001 Controls")
        linked = fetch_linked_controls(tgt['id'])
        if linked:
            for l in linked:
                st.markdown(f"- **{l['id']}**: {l['description']} ({l['status']})")
        else:
            st.info("No controls linked.")
            
        st.divider()
        all_c = fetch_all_iso()
        opts = [f"{c['id']} - {c['description'][:50]}" for c in all_c]
        sel_idx = st.selectbox("Link Control", range(len(opts)), format_func=lambda x: opts[x])
        s_stat = st.selectbox("Status", ["Applicable", "Compliant", "Non-Compliant"])
        s_note = st.text_input("Notes")
        
        if st.form_submit_button("Link Control"):
            cid = all_c[sel_idx]['id']
            link_control(tgt['id'], cid, s_stat, s_note)
            st.success("Linked!")
            st.rerun()
            
    st.divider()

# --- DISPLAY LIST ---
rows = fetch_machines()

if not rows:
    st.info("No computing machines found.")
else:
    # Header
    h0, h1, h2, h3, h4, h5, h6 = st.columns([0.5, 2, 1.5, 1.5, 1.5, 1.5, 2])
    h0.markdown("**#**")
    h1.markdown("**Name**")
    h2.markdown("**IP Address**")
    h3.markdown("**Owner**")
    h4.markdown("**OS**")
    h5.markdown("**Location**")
    h6.markdown("**Actions**")
    st.markdown("---")
    
    for idx, r in enumerate(rows, 1):
        c0, c1, c2, c3, c4, c5, c6 = st.columns([0.5, 2, 1.5, 1.5, 1.5, 1.5, 2])
        c0.write(f"{idx}")
        c1.write(r['name'])
        c2.code(r['ip_address'])
        c3.write(r['owner'])
        c4.write(r['os_type'])
        c5.write(r['location'])
        
        with c6:
            if manage_mode:
                b1, b2, b3 = st.columns(3)
                if b1.button("✏️", key=f"ed_m_{r['id']}", help="Edit"):
                    st.session_state.ecm_edit_target = r
                    st.rerun()
                if b2.button("🗑️", key=f"del_m_{r['id']}", help="Delete"):
                    delete_machine(r['id'])
                    st.success("Deleted")
                    time.sleep(0.5)
                    st.rerun()
                if b3.button("🛡️", key=f"comp_m_{r['id']}", help="Compliance"):
                    st.session_state.ecm_comp_target = r
                    st.rerun()
            else:
                if st.button("🎫 Ticket", key=f"tik_m_{r['id']}"):
                    st.session_state.ecm_ticket_target = r
                    st.rerun()
        st.markdown("---")

    with st.expander("🔍 Source Data"):
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.write("No source data available.")

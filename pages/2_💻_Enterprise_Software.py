
import streamlit as st
import pandas as pd
from database_manager import DatabaseManager
import time

st.set_page_config(layout="wide", page_title="Enterprise Software", page_icon="💻")

st.title("💻 Enterprise Software")
st.markdown("Inventory of Enterprise Software Assets (Layer 7).")

# Initialize Database Manager
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager
db.render_sidebar_status()

# --- STATE MANAGEMENT ---
if 'es_manage_mode' not in st.session_state:
    st.session_state.es_manage_mode = False

if 'es_edit_target' not in st.session_state:
    st.session_state.es_edit_target = None # {id, name, manufacturer, mfa...}

if 'es_ticket_target' not in st.session_state:
    st.session_state.es_ticket_target = None # {id, name...}

if 'es_comp_target' not in st.session_state:
    st.session_state.es_comp_target = None

# --- HELPERS ---
def fetch_software():
    return db.execute("SELECT * FROM kpu_enterprise_software ORDER BY name", fetch=True) or []

def add_software(asset_id, name, manuf, mfa):
    if db.mode == "CLOUD":
        sql = "INSERT INTO kpu_enterprise_software (asset_id, name, manufacturer, mfa_enabled) VALUES (%s, %s, %s, %s)"
        return db.execute(sql, (asset_id, name, manuf, mfa))
    else:
        sql = "INSERT INTO kpu_enterprise_software (asset_id, name, manufacturer, mfa_enabled) VALUES (?, ?, ?, ?)"
        return db.execute(sql, (asset_id, name, manuf, mfa))

def update_software(sid, asset_id, name, manuf, mfa):
    if db.mode == "CLOUD":
        sql = "UPDATE kpu_enterprise_software SET asset_id=%s, name=%s, manufacturer=%s, mfa_enabled=%s WHERE id=%s"
        return db.execute(sql, (asset_id, name, manuf, mfa, sid))
    else:
        sql = "UPDATE kpu_enterprise_software SET asset_id=?, name=?, manufacturer=?, mfa_enabled=? WHERE id=?"
        return db.execute(sql, (asset_id, name, manuf, mfa, sid))

def delete_software(sid):
    return db.execute("DELETE FROM kpu_enterprise_software WHERE id=%s", (sid,)) # execute handles param marker for Delete if simple

def create_software_ticket(sid, t_type, title, desc, prio, status, user):
    return db.create_ticket(sid, t_type, title, desc, prio, user, related_type='software', status=status)

# --- COMPLIANCE HELPERS ---
def fetch_linked_controls(item_id):
    sql = "SELECT ic.*, ac.status FROM iso_controls ic JOIN asset_controls ac ON ic.id = ac.control_id WHERE ac.asset_id=%s AND ac.related_type='software'"
    if db.mode != "CLOUD": sql = sql.replace("%s", "?")
    return db.execute(sql, (item_id,), fetch=True) or []

def link_control(item_id, cid, stat, note):
    # Determine Query
    if db.mode == "CLOUD":
        sql = "INSERT INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (%s, 'software', %s, %s, %s)"
        # Simple Insert for now, duplicates might fail if we fixed index (we didn't fully).
        # Better: Check existence
        check = db.execute("SELECT id FROM asset_controls WHERE asset_id=%s AND related_type='software' AND control_id=%s", (item_id, cid), fetch=True)
        if check:
            sql_up = "UPDATE asset_controls SET status=%s, notes=%s WHERE id=%s"
            return db.execute(sql_up, (stat, note, check[0]['id']))
        else:
            return db.execute(sql, (item_id, cid, stat, note))
    else:
        sql = "INSERT OR REPLACE INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (?, 'software', ?, ?, ?)"
        return db.execute(sql, (item_id, cid, stat, note))

def fetch_all_iso():
    return db.execute("SELECT * FROM iso_controls ORDER BY id", fetch=True) or []

# --- SIDEBAR TOGGLES ---
col_head, col_tog = st.columns([0.8, 0.2])
with col_tog:
    manage_mode = st.toggle("🛠️ Manage Mode", key="es_manage_mode")

# --- MANAGE MODE: ADD/EDIT FORM ---
if manage_mode:
    with st.expander("➕ Add / ✏️ Edit Software", expanded=(st.session_state.es_edit_target is not None or manage_mode)):
        is_edit = st.session_state.es_edit_target is not None
        target = st.session_state.es_edit_target if is_edit else {}
        
        st.caption("Enter software details below.")
        with st.form("software_mgmt_form"):
            c1, c2 = st.columns(2)
            f_name = c1.text_input("Software Name", value=target.get('name', ''))
            f_asset_id = c2.text_input("Asset ID (e.g. CI-123)", value=target.get('asset_id', ''))
            
            c3, c4 = st.columns(2)
            f_manuf = c3.text_input("Manufacturer", value=target.get('manufacturer', ''))
            f_mfa = c4.selectbox("MFA Enabled", ["Yes", "No", "Optional", "N/A"], index=["Yes", "No", "Optional", "N/A"].index(target.get('mfa_enabled', 'N/A')) if target.get('mfa_enabled') in ["Yes", "No", "Optional", "N/A"] else 3)
            
            submitted = st.form_submit_button("Update Software" if is_edit else "Add Software")
            
            if submitted:
                if is_edit:
                    if update_software(target['id'], f_asset_id, f_name, f_manuf, f_mfa):
                        st.success("Updated!")
                        st.session_state.es_edit_target = None
                        st.rerun()
                    else:
                        st.error("Update Failed.")
                else:
                    if add_software(f_asset_id, f_name, f_manuf, f_mfa):
                        st.success("Added!")
                        st.rerun()
                    else:
                        st.error("Add Failed.")
        
        if is_edit:
             if st.button("Cancel Edit"):
                 st.session_state.es_edit_target = None
                 st.rerun()
    st.divider()

# --- TICKET CREATION MODAL ---
if st.session_state.es_ticket_target:
    tgt = st.session_state.es_ticket_target
    with st.form("sw_ticket_form"):
        st.subheader(f"🎫 New Ticket: {tgt['name']}")
        c1, c2 = st.columns(2)
        t_type = c1.selectbox("Type", ["Incident", "Service Request", "Change", "Problem"])
        t_prio = c2.select_slider("Priority", ["Low", "Medium", "High", "Critical"])
        
        t_title = st.text_input("Title")
        t_desc = st.text_area("Description")
        
        c3, c4 = st.columns(2)
        t_status = c3.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
        t_user = c4.text_input("Logged By", value="Admin")
        
        c3, c4 = st.columns(2)
        t_status = c3.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
        t_user = c4.text_input("Logged By", value="Admin")
        
        t_file = st.file_uploader("Attach Document/Image", type=["png", "jpg", "jpeg", "pdf", "docx", "txt"])
        
        if st.form_submit_button("Create Ticket"):
            new_id = create_software_ticket(tgt['id'], t_type, t_title, t_desc, t_prio, t_status, t_user)
            if new_id:
                if t_file:
                    db.save_attachment(new_id, t_file)
                st.success("Ticket Created!")
                st.session_state.es_ticket_target = None
                time.sleep(1)
                st.rerun()
            else:
                st.error("Failed to create ticket.")
                
    if st.button("Cancel Ticket"):
        st.session_state.es_ticket_target = None
        st.rerun()
    st.divider()

# --- COMPLIANCE MODAL ---
if st.session_state.es_comp_target:
    tgt = st.session_state.es_comp_target
    st.subheader(f"🛡️ Compliance: {tgt['name']}")
    if st.button("Close Compliance"):
        st.session_state.es_comp_target = None
        st.rerun()

    with st.form("iso_comp_form"):
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


# --- TABS: INVENTORY vs LICENSES ---
tab_inv, tab_lic = st.tabs(["📦 Software Inventory", "💳 License Management"])

with tab_inv:
    # --- EXISTING INVENTORY VIEW ---
    df = pd.DataFrame(fetch_software())
    if not df.empty:
        # Display as cards or table
        for idx, row in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([0.4, 0.3, 0.15, 0.15])
                with c1:
                    st.subheader(row['name'])
                    st.caption(f"Asset ID: {row['asset_id']}")
                with c2:
                    st.write(f"**Manufacturer:** {row['manufacturer']}")
                    st.write(f"**MFA:** {'✅' if row.get('mfa_enabled') == 'Yes' else '❌'}")
                with c3:
                     # Compliance Badge
                     linked = fetch_linked_controls(row['id'])
                     if linked:
                         non_comp = [l for l in linked if l['status'] == 'Non-Compliant']
                         if non_comp:
                             st.error(f"{len(non_comp)} Gaps")
                         else:
                             st.success("Compliant")
                     else:
                         st.info("No Controls")

                with c4:
                    if manage_mode:
                        # Pass the full row dictionary to es_edit_target
                        st.button("✏️", key=f"ed_{row['id']}", on_click=lambda r=row: setattr(st.session_state, 'es_edit_target', r))
                        if st.button("🗑️", key=f"del_{row['id']}"):
                            delete_software(row['id'])
                            st.rerun()
                        if st.button("🛡️", key=f"comp_{row['id']}"):
                             st.session_state.es_comp_target = {'id': row['id'], 'name': row['name']}
                             st.rerun()
                    else:
                         if st.button("🎫 Ticket", key=f"tik_{row['id']}"):
                             st.session_state.es_ticket_target = {'id': row['id'], 'name': row['name']}
                             st.rerun()
    else:
        st.info("No software assets found.")

with tab_lic:
    st.markdown("### Software Licenses")
    
    # helper
    def get_soft_opts():
        rows = fetch_software()
        return {r['id']: r['name'] for r in rows}
    
    soft_map = get_soft_opts()
    
    if manage_mode:
        with st.expander("➕ Add License Key"):
            with st.form("new_license_form"):
                l_sid = st.selectbox("Software", options=list(soft_map.keys()), format_func=lambda x: soft_map[x])
                l_key = st.text_input("License Key / ID")
                l_vendor = st.text_input("Vendor / Reseller")
                l_total = st.number_input("Total Seats", min_value=1, value=10)
                l_used = st.number_input("Used Seats", min_value=0, value=0)
                l_exp = st.date_input("Expiration Date")
                
                if st.form_submit_button("Add License"):
                    sql = ""
                    if db.mode == "CLOUD":
                        sql = "INSERT INTO software_licenses (software_asset_id, license_key, vendor, total_seats, used_seats, expiration_date) VALUES (%s, %s, %s, %s, %s, %s)"
                    else:
                        sql = "INSERT INTO software_licenses (software_asset_id, license_key, vendor, total_seats, used_seats, expiration_date) VALUES (?, ?, ?, ?, ?, ?)"
                    db.execute(sql, (l_sid, l_key, l_vendor, l_total, l_used, l_exp))
                    st.success("License Added!")
                    st.rerun()

    # View Licenses
    lics = db.execute("SELECT * FROM software_licenses ORDER BY expiration_date", fetch=True)
    if lics:
        for l in lics:
            s_name = soft_map.get(l['software_asset_id'], "Unknown Software")
            with st.container(border=True):
                lc1, lc2, lc3 = st.columns([0.4, 0.4, 0.2])
                with lc1:
                    st.markdown(f"**{s_name}**")
                    st.caption(f"Key: `{l.get('license_key')}`")
                    st.caption(f"Vendor: {l.get('vendor')}")
                
                with lc2:
                    total = l.get('total_seats', 1)
                    used = l.get('used_seats', 0)
                    pct = min(used / total, 1.0)
                    st.progress(pct, text=f"Usage: {used}/{total} Seats")
                    
                    # Expiry Check
                    exp = l.get('expiration_date')
                    if exp:
                         # Handle date/string parsing depending on driver (mysql connector returns date obj, sqlite string)
                         if isinstance(exp, str):
                             exp_dt = pd.to_datetime(exp).date()
                         else:
                             exp_dt = exp # mysql date object
                             
                         days_left = (exp_dt - datetime.now().date()).days
                         if days_left < 0:
                             st.error(f"Expired {abs(days_left)} days ago! ({exp})")
                         elif days_left < 30:
                             st.warning(f"Expiring in {days_left} days ({exp})")
                         else:
                             st.success(f"Valid until {exp}")

                with lc3:
                    if manage_mode:
                        if st.button("🗑️", key=f"del_lic_{l['id']}"):
                            db.execute(f"DELETE FROM software_licenses WHERE id={l['id']}")
                            st.rerun()
    else:
        st.info("No licenses tracked.")
```

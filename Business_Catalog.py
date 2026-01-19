
import streamlit as st
from database_manager import DatabaseManager
import time

# =============================================================================
# Page: Business Catalog (Landing Page)
# =============================================================================
# Displays the new Strict Hierarchy of Services and Assets.
# 1. Business Service L1
# 2. Business Service L2
# 3. Technical Service
# 4. Enterprise Asset
# 5. Component Asset
# =============================================================================

st.set_page_config(page_title="2D Mandrake - Service Management & Compliance", page_icon="🌳", layout="wide")

st.title("🌳 2D Mandrake - Service Management & Compliance")
st.markdown("""
Reflects the **strict 5-level schema**:
`Business Service L1` ➡️ `Business Service L2` ➡️ `Technical Service` ➡️ `Enterprise Asset` ➡️ `Component Asset`
""")

# Initialize Database Manager
# Checks for stale instances (missing new methods like get_storage_config) and re-initializes
if 'db_manager' not in st.session_state or not hasattr(st.session_state.db_manager, 'get_storage_config'):
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager

# Render Global Sidebar (Cloud Status + Sync Buttons)
db.render_sidebar_status()

def execute(query, params=None):
    return st.session_state.db_manager.execute(query, params, fetch=True)

# --- Fetch Data (Hierarchical Fetch) ---
def get_hierarchy():
    # 1. Level 1
    l1_rows = execute("SELECT * FROM kpu_business_services_level1 ORDER BY name") or []
    
    # 2. Level 2
    l2_rows = execute("SELECT * FROM kpu_business_services_level2 ORDER BY name") or []
    l2_map = {}
    for r in l2_rows:
        pid = r['business_service_level1_id']
        if pid not in l2_map: l2_map[pid] = []
        l2_map[pid].append(r)

    # 3. Technical Services
    ts_rows = execute("SELECT * FROM kpu_technical_services ORDER BY name") or []
    ts_map = {}
    for r in ts_rows:
        pid = r['business_service_level2_id']
        if pid not in ts_map: ts_map[pid] = []
        ts_map[pid].append(r)
        
    # 4. Enterprise Assets
    ea_rows = execute("SELECT * FROM kpu_enterprise_assets ORDER BY name") or []
    ea_map = {}
    for r in ea_rows:
        pid = r['technical_service_id']
        if pid not in ea_map: ea_map[pid] = []
        ea_map[pid].append(r)
        
    # 5. Component Assets
    ca_rows = execute("SELECT * FROM kpu_component_assets ORDER BY name") or []
    ca_map = {}
    for r in ca_rows:
        pid = r['enterprise_asset_id']
        if pid not in ca_map: ca_map[pid] = []
        ca_map[pid].append(r)
        
    return l1_rows, l2_map, ts_map, ea_map, ca_map

# --- Session State Setup ---
if 'add_context' not in st.session_state:
    st.session_state.add_context = {'level': "Business Service L1", 'parent_id': None, 'parent_name': None}

if 'edit_context' not in st.session_state:
    st.session_state.edit_context = {'active': False, 'level': None, 'id': None, 'data': {}} 

if 'manage_mode_toggle' not in st.session_state:
    st.session_state['manage_mode_toggle'] = False

if 'add_entry_level_select' not in st.session_state:
    st.session_state['add_entry_level_select'] = "Business Service L1"

if 'form_reset_key' not in st.session_state:
    st.session_state['form_reset_key'] = 0

if 'sc_comp_target' not in st.session_state:
    st.session_state.sc_comp_target = None # {id, type, name}

if 'sc_ticket_target' not in st.session_state:
    st.session_state.sc_ticket_target = None # {id, type, name}

# --- Callbacks ---
def set_add_context(level, p_id, p_name):
    st.session_state.edit_context['active'] = False
    st.session_state.add_context = {'level': level, 'parent_id': p_id, 'parent_name': p_name}
    st.session_state['add_entry_level_select'] = level
    st.session_state['manage_mode_toggle'] = True 
    st.session_state['form_reset_key'] += 1

def set_edit_context(level, item_id, item_data):
    st.session_state.edit_context = {'active': True, 'level': level, 'id': item_id, 'data': item_data}
    st.session_state['add_entry_level_select'] = level
    st.session_state['manage_mode_toggle'] = True 
    st.session_state['form_reset_key'] += 1
    
def clear_edit_context():
    st.session_state.edit_context['active'] = False
    st.session_state.add_context['parent_id'] = None 
    st.session_state['form_reset_key'] += 1

def delete_item(table, item_id):
    try:
        st.session_state.db_manager.execute(f"DELETE FROM {table} WHERE id = %s", (item_id,))
        st.toast("Item Deleted!", icon="🗑️")
    except Exception as e:
        st.error(f"Delete Failed: {e}")

def set_comp_target(item_id, item_type, item_name):
    st.session_state.sc_comp_target = {'id': item_id, 'type': item_type, 'name': item_name}

def set_ticket_target(item_id, item_type, item_name):
    st.session_state.sc_ticket_target = {'id': item_id, 'type': item_type, 'name': item_name}

def create_catalog_ticket(asset_id, related_type, t_type, title, desc, prio, status, user):
    # Delegate to Centralized Manager (enforces SLA logic)
    # Mapping args: asset_id, ticket_type, title, description, priority, logged_by, related_type, status
    return db.create_ticket(asset_id, t_type, title, desc, prio, user, related_type, status)

# --- COMPLIANCE HELPERS ---
def fetch_linked_controls(item_id, item_type):
    # Retrieve dynamic type
    sql = "SELECT ic.*, ac.status FROM iso_controls ic JOIN asset_controls ac ON ic.id = ac.control_id WHERE ac.asset_id=%s AND ac.related_type=%s"
    if db.mode != "CLOUD": sql = sql.replace("%s", "?")
    return db.execute(sql, (item_id, item_type), fetch=True) or []

def link_control(item_id, item_type, cid, stat, note):
    if db.mode == "CLOUD":
        sql = "INSERT INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (%s, %s, %s, %s, %s)"
        check = db.execute("SELECT id FROM asset_controls WHERE asset_id=%s AND related_type=%s AND control_id=%s", (item_id, item_type, cid), fetch=True)
        if check:
            sql_up = "UPDATE asset_controls SET status=%s, notes=%s WHERE id=%s"
            return db.execute(sql_up, (stat, note, check[0]['id']))
        else:
            return db.execute(sql, (item_id, item_type, cid, stat, note))
    else:
        sql = "INSERT OR REPLACE INTO asset_controls (asset_id, related_type, control_id, status, notes) VALUES (?, ?, ?, ?, ?)"
        return db.execute(sql, (item_id, item_type, cid, stat, note))

def fetch_all_iso():
    return db.execute("SELECT * FROM iso_controls ORDER BY id", fetch=True) or []


# --- Render Tree ---
l1_rows, l2_map, ts_map, ea_map, ca_map = get_hierarchy()

# Management Toggle
col_h, col_t = st.columns([0.8, 0.2])
with col_t:
    manage_mode = st.toggle("🛠️ Manage Mode", key='manage_mode_toggle')

# --- TICKET MODAL ---
if st.session_state.sc_ticket_target:
    tgt = st.session_state.sc_ticket_target
    with st.form("sc_ticket_form"):
        st.subheader(f"🎫 New Ticket: {tgt['name']}")
        st.caption(f"Type: {tgt['type']}")
        
        c1, c2 = st.columns(2)
        t_type = c1.selectbox("Type", ["Incident", "Service Request", "Change", "Problem"])
        t_prio = c2.select_slider("Priority", ["Low", "Medium", "High", "Critical"])
        
        t_title = st.text_input("Title")
        t_desc = st.text_area("Description")
        
        c3, c4 = st.columns(2)
        t_status = c3.selectbox("Status", ["Open", "In Progress", "Resolved", "Closed"])
        t_user = c4.text_input("Logged By", value="Admin")
        
        t_file = st.file_uploader("Attach Document/Image", type=["png", "jpg", "jpeg", "pdf", "docx", "txt"])
        
        if st.form_submit_button("Create Ticket"):
            new_id = create_catalog_ticket(tgt['id'], tgt['type'], t_type, t_title, t_desc, t_prio, t_status, t_user)
            if new_id:
                if t_file:
                    if db.save_attachment(new_id, t_file):
                        st.success("Ticket & Attachment Created!")
                    else:
                        st.warning("Ticket created, but attachment upload failed.")
                else:
                    st.success("Ticket Created!")
                
                st.session_state.sc_ticket_target = None
                time.sleep(1)
                st.rerun()
            else:
                st.error("Failed to create ticket.")
                
    if st.button("Cancel Ticket"):
        st.session_state.sc_ticket_target = None
        st.rerun()
    st.divider()

# --- COMPLIANCE MODAL ---
if st.session_state.sc_comp_target:
    tgt = st.session_state.sc_comp_target
    st.subheader(f"🛡️ Compliance: {tgt['name']}")
    if st.button("Close Compliance"):
        st.session_state.sc_comp_target = None
        st.rerun()

    with st.form("iso_comp_form_sc"):
        st.caption(f"ISO 27001 (Type: {tgt['type']})")
        linked = fetch_linked_controls(tgt['id'], tgt['type'])
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
            link_control(tgt['id'], tgt['type'], cid, s_stat, s_note)
            st.success("Linked!")
            st.rerun()
          
    st.divider()


if manage_mode:
    st.divider()
    is_editing = st.session_state.edit_context.get('active', False)
    form_label = "✏️ Edit Entry" if is_editing else "➕ Add New Entry"
    
    with st.expander(form_label, expanded=True):
        # Level Select
        entry_type = st.selectbox("Level", ["Business Service L1", "Business Service L2", "Technical Service", "Enterprise Asset", "Component Asset"], key='add_entry_level_select', disabled=is_editing)
        
        # ... [Same Form Logic as before, just kept concise] ...
        # (I will implement the FULL form logic here to ensure it's not lost)
        
        # Helper
        def get_parent_index(opts_dict, target_id):
            if target_id is None: return 0
            values = list(opts_dict.values())
            try:
                if target_id in values: return values.index(target_id)
            except: return 0
            return 0

        with st.form("hierarchy_entry_form"):
            edit_data = st.session_state.edit_context.get('data', {}) if is_editing else {}
            frk = st.session_state['form_reset_key']
            
            if entry_type == "Business Service L1":
                st.caption("Table: `kpu_business_services_level1`")
                n_name = st.text_input("Name", value=edit_data.get('name', ''), key=f"l1_name_{frk}")
                n_desc = st.text_area("Description", value=edit_data.get('description', ''), key=f"l1_desc_{frk}")
                n_owner = st.text_input("Owner", value=edit_data.get('owner', ''), key=f"l1_owner_{frk}")
                
                c_submit, c_cancel = st.columns([0.2, 0.8])
                submitted = c_submit.form_submit_button("Update" if is_editing else "Add")
                if is_editing: c_cancel.form_submit_button("Cancel", on_click=clear_edit_context)
                
                if submitted:
                    if is_editing:
                        st.session_state.db_manager.execute("UPDATE kpu_business_services_level1 SET name=%s, description=%s, owner=%s WHERE id=%s", (n_name, n_desc, n_owner, st.session_state.edit_context['id']))
                        st.success("Updated!"); clear_edit_context()
                    else:
                        st.session_state.db_manager.execute("INSERT INTO kpu_business_services_level1 (name, description, owner) VALUES (%s, %s, %s)", (n_name, n_desc, n_owner))
                        st.success("Added!"); st.session_state['form_reset_key'] += 1
                    st.rerun()

            elif entry_type == "Business Service L2":
                st.caption("Table: `kpu_business_services_level2`")
                l1_opts = {r['name']: r['id'] for r in l1_rows}
                if l1_opts:
                    curr_pid = edit_data.get('business_service_level1_id') if is_editing else st.session_state.add_context.get('parent_id')
                    p_name = st.selectbox("Parent", list(l1_opts.keys()), index=get_parent_index(l1_opts, curr_pid), disabled=is_editing, key=f"l2_p_{frk}") 
                    n_name = st.text_input("Name", value=edit_data.get('name', ''), key=f"l2_n_{frk}")
                    n_desc = st.text_area("Description", value=edit_data.get('description', ''), key=f"l2_d_{frk}")
                    submitted = st.form_submit_button("Update" if is_editing else "Add")
                    if submitted:
                        if is_editing:
                            st.session_state.db_manager.execute("UPDATE kpu_business_services_level2 SET name=%s, description=%s WHERE id=%s", (n_name, n_desc, st.session_state.edit_context['id']))
                            st.success("Updated!"); clear_edit_context()
                        else:
                            st.session_state.db_manager.execute("INSERT INTO kpu_business_services_level2 (business_service_level1_id, name, description) VALUES (%s, %s, %s)", (l1_opts[p_name], n_name, n_desc))
                            st.success("Added!"); st.session_state['form_reset_key'] += 1
                        st.rerun()

            elif entry_type == "Technical Service":
                st.caption("Table: `kpu_technical_services`")
                l2_flat = [x for sub in l2_map.values() for x in sub]
                l2_opts = {r['name']: r['id'] for r in l2_flat}
                if l2_opts:
                    curr_pid = edit_data.get('business_service_level2_id') if is_editing else st.session_state.add_context.get('parent_id')
                    p_name = st.selectbox("Parent", list(l2_opts.keys()), index=get_parent_index(l2_opts, curr_pid), disabled=is_editing)
                    n_name = st.text_input("Name", value=edit_data.get('name', ''))
                    n_desc = st.text_area("Description", value=edit_data.get('description', ''))
                    n_sla = st.selectbox("SLA", ["Platinum", "Gold", "Silver", "Bronze"], index=["Platinum", "Gold", "Silver", "Bronze"].index(edit_data.get('sla_level', 'Bronze')))
                    
                    submitted = st.form_submit_button("Update" if is_editing else "Add")
                    if submitted:
                        if is_editing:
                            st.session_state.db_manager.execute("UPDATE kpu_technical_services SET name=%s, description=%s, sla_level=%s WHERE id=%s", (n_name, n_desc, n_sla, st.session_state.edit_context['id']))
                            st.success("Updated!"); clear_edit_context()
                        else:
                            st.session_state.db_manager.execute("INSERT INTO kpu_technical_services (business_service_level2_id, name, description, sla_level) VALUES (%s, %s, %s, %s)", (l2_opts[p_name], n_name, n_desc, n_sla))
                            st.success("Added!")
                        st.rerun()

            elif entry_type == "Enterprise Asset":
                st.caption("Table: `kpu_enterprise_assets`")
                ts_flat = [x for sub in ts_map.values() for x in sub]
                ts_opts = {r['name']: r['id'] for r in ts_flat}
                if ts_opts:
                    curr_pid = edit_data.get('technical_service_id') if is_editing else st.session_state.add_context.get('parent_id')
                    p_name = st.selectbox("Parent", list(ts_opts.keys()), index=get_parent_index(ts_opts, curr_pid), disabled=is_editing)
                    n_name = st.text_input("Name", value=edit_data.get('name', ''))
                    n_type = st.selectbox("Type", ["Server", "Database", "Appliance", "Router", "Switch", "Storage", "Cloud Resource"], index=0) # simplified
                    n_loc = st.text_input("Location", value=edit_data.get('location', ''))
                    
                    submitted = st.form_submit_button("Update" if is_editing else "Add")
                    if submitted:
                        if is_editing:
                            st.session_state.db_manager.execute("UPDATE kpu_enterprise_assets SET name=%s, asset_type=%s, location=%s WHERE id=%s", (n_name, n_type, n_loc, st.session_state.edit_context['id']))
                            st.success("Updated!"); clear_edit_context()
                        else:
                            st.session_state.db_manager.execute("INSERT INTO kpu_enterprise_assets (technical_service_id, name, asset_type, location) VALUES (%s, %s, %s, %s)", (ts_opts[p_name], n_name, n_type, n_loc))
                            st.success("Added!")
                        st.rerun()

            elif entry_type == "Component Asset":
                st.caption("Table: `kpu_component_assets`")
                ea_flat = [x for sub in ea_map.values() for x in sub]
                ea_opts = {r['name']: r['id'] for r in ea_flat}
                if ea_opts:
                    curr_pid = edit_data.get('enterprise_asset_id') if is_editing else st.session_state.add_context.get('parent_id')
                    p_name = st.selectbox("Parent", list(ea_opts.keys()), index=get_parent_index(ea_opts, curr_pid), disabled=is_editing)
                    n_name = st.text_input("Name", value=edit_data.get('name', ''))
                    n_type = st.text_input("Type", value=edit_data.get('component_type', 'Module'))
                    n_ver = st.text_input("Version", value=edit_data.get('version', ''))
                    n_desc = st.text_area("Description", value=edit_data.get('description', ''))
                    
                    submitted = st.form_submit_button("Update" if is_editing else "Add")
                    if submitted:
                        if is_editing:
                            st.session_state.db_manager.execute("UPDATE kpu_component_assets SET name=%s, component_type=%s, version=%s, description=%s WHERE id=%s", (n_name, n_type, n_ver, n_desc, st.session_state.edit_context['id']))
                            st.success("Updated!"); clear_edit_context()
                        else:
                            st.session_state.db_manager.execute("INSERT INTO kpu_component_assets (enterprise_asset_id, name, component_type, version, description) VALUES (%s, %s, %s, %s, %s)", (ea_opts[p_name], n_name, n_type, n_ver, n_desc))
                            st.success("Added!")
                        st.rerun()
    st.divider()

if not l1_rows:
    st.info("No hierarchy data found. Add a Level 1 Service above!")
else:
    for l1 in l1_rows:
        # LEVEL 1
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            with st.expander(f"🏢 **{l1['name']}**  _(Owner: {l1['owner']})_", expanded=True):
                 st.caption((l1['description'] or "").replace("\n", "  \n"))
                 
                 l2_services = l2_map.get(l1['id'], [])
                 if not l2_services: st.caption("No Level 2 services.")
                 for l2 in l2_services:
                     # LEVEL 2
                     cc1, cc2 = st.columns([0.8, 0.2])
                     with cc1:
                         st.markdown(f"#### 📂 {l2['name']}")
                         st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;{(l2['description'] or '').replace(chr(10), '  '+chr(10))}")
                     with cc2:
                         if manage_mode:
                             st.button("✏️", key=f"ed_l2_{l2['id']}", help="Edit L2", on_click=set_edit_context, args=("Business Service L2", l2['id'], l2))
                             st.button("🗑️", key=f"del_l2_{l2['id']}", help="Delete L2", on_click=delete_item, args=("kpu_business_services_level2", l2['id']))
                             st.button("➕ TS", key=f"add_ts_{l2['id']}", help="Add TS", on_click=set_add_context, args=("Technical Service", l2['id'], l2['name']))
                         else:
                             if st.button("🎫 Ticket", key=f"tik_l2_{l2['id']}"):
                                 set_ticket_target(l2['id'], "kpu_business_services_level2", l2['name'])
                                 st.rerun()

                     tech_services = ts_map.get(l2['id'], [])
                     for ts in tech_services:
                         # LEVEL 3
                         tc1, tc2 = st.columns([0.8, 0.2])
                         with tc1:
                             st.markdown(f"<div style='margin-left:20px; border-left:2px solid #ddd; padding-left:10px;'><b>⚙️ {ts['name']}</b> <span style='background:#eee;padding:2px;'>SLA: {ts['sla_level']}</span><br><small>{ts['description']}</small></div>", unsafe_allow_html=True)
                         with tc2:
                            if manage_mode:
                                st.button("✏️", key=f"ed_ts_{ts['id']}", help="Edit", on_click=set_edit_context, args=("Technical Service", ts['id'], ts))
                                st.button("🗑️", key=f"del_ts_{ts['id']}", help="Delete", on_click=delete_item, args=("kpu_technical_services", ts['id']))
                                # Compliance for Technical Service
                                st.button("🛡️", key=f"comp_ts_{ts['id']}", help="Compliance", on_click=set_comp_target, args=(ts['id'], "kpu_technical_services", ts['name']))
                                st.button("➕ Asset", key=f"add_ea_{ts['id']}", help="Add Asset", on_click=set_add_context, args=("Enterprise Asset", ts['id'], ts['name']))
                            else:
                                if st.button("🎫 Ticket", key=f"tik_ts_{ts['id']}"):
                                    set_ticket_target(ts['id'], "kpu_technical_services", ts['name'])
                                    st.rerun()
                            
                         ent_assets = ea_map.get(ts['id'], [])
                         for ea in ent_assets:
                                 with st.container():
                                     c_ea1, c_ea2 = st.columns([0.05, 0.95])
                                     with c_ea2:
                                         ec1, ec2 = st.columns([0.8, 0.2])
                                         with ec1:
                                            st.markdown(f"**🖥️ {ea['name']}** - `{ea['asset_type']}`")
                                         with ec2:
                                            if manage_mode:
                                                st.button("✏️", key=f"ed_ea_{ea['id']}", help="Edit", on_click=set_edit_context, args=("Enterprise Asset", ea['id'], ea))
                                                st.button("🗑️", key=f"del_ea_{ea['id']}", help="Delete", on_click=delete_item, args=("kpu_enterprise_assets", ea['id']))
                                                # Compliance for Enterprise Asset
                                                st.button("🛡️", key=f"comp_ea_{ea['id']}", help="Compliance", on_click=set_comp_target, args=(ea['id'], "kpu_enterprise_assets", ea['name']))
                                                st.button("➕ Comp", key=f"add_ca_{ea['id']}", help="Add Comp", on_click=set_add_context, args=("Component Asset", ea['id'], ea['name']))
                                            else:
                                                if st.button("🎫 Ticket", key=f"tik_ea_{ea['id']}"):
                                                    set_ticket_target(ea['id'], "kpu_enterprise_assets", ea['name'])
                                                    st.rerun()
                                         
                                         comps = ca_map.get(ea['id'], [])
                                         if comps:
                                             st.markdown("**Components:**")
                                             for c in comps:
                                                 cc_1, cc_2 = st.columns([0.8, 0.2])
                                                 cc_1.markdown(f"🧩 {c['name']} ({c['component_type']})")
                                                 with cc_2:
                                                     if manage_mode:
                                                         st.button("✏️", key=f"ed_ca_{c['id']}", help="Edit", on_click=set_edit_context, args=("Component Asset", c['id'], c))
                                                         st.button("🗑️", key=f"del_ca_{c['id']}", help="Delete", on_click=delete_item, args=("kpu_component_assets", c['id']))
                                                     else:
                                                         if st.button("🎫 Ticket", key=f"tik_ca_{c['id']}"):
                                                             set_ticket_target(c['id'], "kpu_component_assets", c['name'])
                                                             st.rerun()
                                     st.divider()

        with c2:
            if manage_mode:
                st.button("✏️", key=f"ed_l1_{l1['id']}", help="Edit L1", on_click=set_edit_context, args=("Business Service L1", l1['id'], l1))
                st.button("🗑️", key=f"del_l1_{l1['id']}", help="Delete L1", on_click=delete_item, args=("kpu_business_services_level1", l1['id']))
                st.button("➕ L2", key=f"add_l2_{l1['id']}", help="Add L2", on_click=set_add_context, args=("Business Service L2", l1['id'], l1['name']))
            else:
                if st.button("🎫 Ticket", key=f"tik_l1_{l1['id']}"):
                    set_ticket_target(l1['id'], "kpu_business_services_level1", l1['name'])
                    st.rerun()

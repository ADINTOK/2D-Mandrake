import streamlit as st
import pandas as pd
import database_manager
import importlib
import time

# Force reload to get new methods
importlib.reload(database_manager)
from database_manager import DatabaseManager

st.set_page_config(page_title="Policy Manager", page_icon="📜", layout="wide")

st.title("📜 Policy Manager")
st.info("""
**Governance, Risk, and Compliance (GRC)**
Define and manage internal security policies. Map them to industry standards (NIST, ISO) 
to demonstrate compliance coverage.
""")

# Initialize DB
# Check for stale manager (missing new methods)
if 'db_manager' in st.session_state:
    if not hasattr(st.session_state.db_manager, 'get_nist_controls'):
        del st.session_state.db_manager
        st.rerun()

if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

db = st.session_state.db_manager
db.render_sidebar_status()

# Tabs
tab_list, tab_create, tab_matrix = st.tabs(["📋 Policy List", "➕ Create Policy", "🕸️ Traceability Matrix"])

with tab_create:
    st.header("Define New Policy")
    with st.form("create_policy_form"):
        p_name = st.text_input("Policy Name", placeholder="e.g. Access Control Policy")
        c1, c2 = st.columns(2)
        with c1:
            p_cat = st.selectbox("Category", ["Information Security", "HR", "IT Operations", "Data Privacy", "Physical Security"])
        with c2:
            p_sum = st.text_input("Summary/Purpose", placeholder="Brief description of intent")
            
        p_content = st.text_area("Policy Content (Markdown)", height=300, placeholder="## 1. Overview\nAccess to systems...")
        
        st.markdown("### Compliance Mapping (NIST CSF)")
        # Fetch NIST Controls
        nist_controls = db.get_nist_controls()
        nist_options = {f"{n['id']} - {n['function']}/{n['category']}": n['id'] for n in nist_controls} if nist_controls else {}
        
        selected_nist = st.multiselect("Map to NIST Controls", options=nist_options.keys())
        
        submitted = st.form_submit_button("Create Policy", type="primary")
        
        if submitted:
            if not p_name:
                st.error("Policy Name is required.")
            else:
                success, msg = db.create_policy(p_name, p_cat, p_sum, p_content)
                if success:
                    # Get ID (hacky fetch last)
                    # Ideally create_policy should return ID. 
                    # Assuming lookup by name/recent for now or just creating.
                    # Mapping:
                    latest = db.execute(f"SELECT id FROM policies WHERE name='{p_name}' ORDER BY created_at DESC LIMIT 1", fetch=True)
                    if latest:
                        pid = latest[0]['id']
                        if selected_nist:
                            count = 0
                            for label in selected_nist:
                                nid = nist_options[label]
                                db.link_policy_to_nist(pid, nid)
                                count += 1
                            st.success(f"✅ Policy Created and mapped to {count} controls!")
                        else:
                            st.success("✅ Policy Created (No mappings).")
                    else:
                        st.success("✅ Policy Created.")
                        
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Failed: {msg}")

with tab_list:
    policies = db.get_policies()
    if not policies:
        st.info("No Policies Defined. Go to 'Create Policy' to start.")
    else:
        for p in policies:
            with st.expander(f"📜 {p['name']} ({p['category']})"):
                st.caption(f"ID: {p['id']} | Created: {p['created_at']}")
                st.markdown(f"**Summary:** {p['summary']}")
                st.divider()
                st.markdown(p['content'])
                
                # Show Mappings
                mappings = db.get_policy_mappings(p['id'])
                if mappings:
                    st.markdown("#### ✅ Mapped Controls")
                    st.write([m['nist_control_id'] for m in mappings])

with tab_matrix:
    st.header("Traceability Matrix")
    st.caption("Visualizing coverage of NIST Controls by Policies.")
    
    # Simple Matrix
    if st.button("Generate Matrix"):
        # Get all mappings
        all_maps = db.execute("SELECT * FROM policy_nist_mappings", fetch=True)
        if all_maps:
            df = pd.DataFrame(all_maps)
            st.dataframe(df, use_container_width=True)
            
            # Group by NIST
            cov = df.groupby('nist_control_id').count()
            st.bar_chart(cov)
        else:
            st.warning("No mappings found.")

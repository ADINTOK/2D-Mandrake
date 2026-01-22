import streamlit as st
import sys
import os
import subprocess

st.set_page_config(page_title="Distribution Manager", page_icon="📦")

def get_dir_size(start_path = '.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

st.title("📦 Distribution Manager")
st.info("""
**Project Portability & Deployment**
Standardize and package your Mandrake environment for sharing or remote deployment. 
This module identifies environment bloat (virtual environments, caches) and provides automated tools to build slim, ready-to-use distributions.
""")

# --- Calculations ---
# We assume this script is running from the root of the project generally
# but if running as a page, we might need to look up one level if we want project root.
# However, streamlit usually runs from project root.
total_size_raw = get_dir_size('.')
venv_size = get_dir_size('./venv') if os.path.exists('./venv') else 0
cache_size = 0
for root, dirs, files in os.walk('.'):
    if '__pycache__' in dirs:
        cache_size += get_dir_size(os.path.join(root, '__pycache__'))

slim_size_est = total_size_raw - venv_size - cache_size

# --- UI: Size Comparison ---
c1, c2, c3 = st.columns(3)
c1.metric("Current Total", f"{total_size_raw / (1024*1024):.2f} MB")
c2.metric("Environment Bloat", f"{(venv_size + cache_size) / (1024*1024):.2f} MB", delta_color="inverse")
c3.metric("Estimated Slim Zip", f"{slim_size_est / (1024*1024):.2f} MB", delta=f"-{((venv_size + cache_size) / total_size_raw * 100):.1f}%")

st.divider()

# --- Actions ---
col_zip, col_clean = st.columns(2)

with col_zip:
    st.subheader("🚀 Automation")
    st.write("Generate a ready-to-distribute ZIP file instantly.")
    if st.button("📦 Build Slim Distribution Zip", type="primary", use_container_width=True):
        with st.spinner("Building zip..."):
            try:
                # Run the Python Build Script (Faster/Cross-Platform)
                # Ensure build_distribution.py exists in root
                target_script = "build_distribution.py"
                if not os.path.exists(target_script):
                     # Try one level up if we are in pages? No, cwd usually root
                     st.error(f"Build script '{target_script}' not found in {os.getcwd()}")
                else:
                    cmd = [sys.executable, target_script]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        st.success("✅ Build Successful!")
                        st.code(result.stdout)
                    else:
                        st.error("❌ Build Failed")
                        st.code(result.stderr)
            except Exception as e:
                st.error(f"Error launching build script: {e}")

with col_clean:
    st.subheader("🧹 Maintenance")
    st.write("Wipe your local environment and caches to save disk space.")
    st.info("💡 **Manual Action Required**: Run `Clean_Project.bat` manually.")

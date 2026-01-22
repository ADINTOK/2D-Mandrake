
import sys
import os
import csv
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database_manager import DatabaseManager

def import_layer7(csv_path):
    print(f"Importing from {csv_path}...")
    
    if not os.path.exists(csv_path):
        st.error(f"File not found: {csv_path}")
        return

    # Initialize DatabaseManager
    # Automated SSH Tunneling
    db = DatabaseManager()

    # Mapping:
    # Asset_ID -> asset_id
    # Name -> name
    # Manufacturer -> manufacturer
    # MFA Enabled -> mfa_enabled

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        
        if not headers:
            st.error("CSV is empty or missing headers.")
            return

        def get_idx(col_name):
            try:
                return headers.index(col_name)
            except ValueError:
                return -1

        idx_id = get_idx("Asset_ID")
        idx_name = get_idx("Name")
        idx_manuf = get_idx("Manufacturer")
        idx_mfa = get_idx("MFA Enabled")
        
        count = 0
        success = 0
        
        sql = """
            INSERT INTO kpu_enterprise_software 
            (asset_id, name, manufacturer, mfa_enabled)
            VALUES (%s, %s, %s, %s)
        """
        
        for row in reader:
            count += 1
            try:
                name = row[idx_name].strip() if idx_name != -1 and len(row) > idx_name else f"Unknown Software {count}"
                asset_id = row[idx_id].strip() if idx_id != -1 and len(row) > idx_id else ""
                manuf = row[idx_manuf].strip() if idx_manuf != -1 and len(row) > idx_manuf else ""
                mfa = row[idx_mfa].strip() if idx_mfa != -1 and len(row) > idx_mfa else "No"
                
                # Normalize MFA
                if mfa.lower() in ['yes', 'true', '1']: mfa = 'Yes'
                elif mfa.lower() in ['no', 'false', '0']: mfa = 'No'

                if not name: continue

                db.execute(sql, (asset_id, name, manuf, mfa))
                success += 1
                
            except Exception as e:
                print(f"Error row {count}: {e}")

        st.success(f"Successfully imported {success} out of {count} software assets into `kpu_enterprise_software`.")

if __name__ == "__main__":
    st.title("Admin Tool: Import Layer 7 Software")
    # Auto-run
    # C:\Users\Anand\Downloads\KPU_MasterAsset_List - Layer7List.csv
    target_csv = r"C:\Users\Anand\Downloads\KPU_MasterAsset_List - Layer7List.csv"
    import_layer7(target_csv)

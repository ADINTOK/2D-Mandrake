
import sys
import os
import csv
import streamlit as st

# Add parent directory to path to import database_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_manager import DatabaseManager

def import_safelist(csv_path):
    print(f"Importing from {csv_path}...")
    
    if not os.path.exists(csv_path):
        st.error(f"File not found: {csv_path}")
        return

    # Initialize DatabaseManager
    # It will handle secrets loading and SSH tunneling automatically
    db = DatabaseManager()
    
    if db.mode != "CLOUD":
        st.warning("Not connected to Cloud DB. Data will be saved locally (if supported) or import might fail if target table is cloud-only.")
        # Proceeding anyway as DatabaseManager abstracts this, but good to warn.

    # Mapping:
    # Asset_Name -> name
    # Asset_ID -> asset_id
    # Primary IP Address -> ip_address
    # Primary MAC Address -> mac_address
    # Primary Owner -> owner
    # OS Type -> os_type
    # Location -> location
    
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

        idx_name = get_idx("Asset_Name")
        idx_asset_id = get_idx("Asset_ID")
        idx_ip = get_idx("Primary IP Address")
        idx_mac = get_idx("Primary MAC Address")
        idx_owner = get_idx("Primary Owner")
        idx_os = get_idx("OS Type")
        idx_loc = get_idx("Location")
        
        count = 0
        success = 0
        
        sql = """
            INSERT INTO kpu_enterprise_computing_machines 
            (name, asset_id, ip_address, mac_address, owner, os_type, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        for row in reader:
            count += 1
            try:
                name = row[idx_name].strip() if idx_name != -1 and len(row) > idx_name else f"Unknown Device {count}"
                asset_id = row[idx_asset_id].strip() if idx_asset_id != -1 and len(row) > idx_asset_id else ""
                ip = row[idx_ip].strip() if idx_ip != -1 and len(row) > idx_ip else ""
                mac = row[idx_mac].strip() if idx_mac != -1 and len(row) > idx_mac else ""
                owner = row[idx_owner].strip() if idx_owner != -1 and len(row) > idx_owner else ""
                os_type = row[idx_os].strip() if idx_os != -1 and len(row) > idx_os else ""
                location = row[idx_loc].strip() if idx_loc != -1 and len(row) > idx_loc else ""

                if not name:
                   if mac: name = f"Device-{mac}"
                   else: continue

                # Use db.execute
                db.execute(sql, (name, asset_id, ip, mac, owner, os_type, location))
                success += 1
                
            except Exception as e:
                print(f"Error row {count}: {e}")

        st.success(f"Successfully imported {success} out of {count} devices into `kpu_enterprise_computing_machines`.")

if __name__ == "__main__":
    st.title("Admin Tool: Import SafeList")
    # Auto-run for agentic execution
    target_csv = r"C:\Users\Anand\Downloads\KPU_MasterAsset_List - SafeListDevices.csv"
    import_safelist(target_csv)

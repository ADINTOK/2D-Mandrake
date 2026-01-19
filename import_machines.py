
import pandas as pd
from database_manager import DatabaseManager
import streamlit as st

def import_data():
    print("Starting import for Enterprise Computing Machines...")
    csv_path = r"C:\Users\Anand\Downloads\KPU_MasterAsset_List - SafeListDevices.csv"
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    db = DatabaseManager()
    
    # Expected columns mappings
    # Asset_ID -> asset_id
    # Asset_Name -> name
    # Primary IP Address -> ip_address
    # Primary MAC Address -> mac_address
    # Primary Owner -> owner
    # OS Type -> os_type
    # last_location OR Location -> location (prioritize last_location)
    
    count = 0
    
    # Use cloud connection if available, else local
    conn = db._get_cloud_conn()
    if not conn:
        print("Using LOCAL connection")
        conn = db._get_local_conn()
    else:
        print("Using CLOUD connection")

    cursor = conn.cursor()

    for index, row in df.iterrows():
        # Clean data
        asset_id = str(row.get('Asset_ID', '')).strip()
        if asset_id in ['nan', 'None']: asset_id = ''
        
        name = str(row.get('Asset_Name', '')).strip()
        if name in ['nan', 'None']: name = ''
        
        # If no name, try to use Host Name or similar if available, or skip
        if not name: 
            host = str(row.get('EndPoint Name', '')).strip()
            if host and host != 'nan':
                name = host
            else:
                continue # Skip effectively empty rows
        
        ip_addr = str(row.get('Primary IP Address', '')).strip()
        if ip_addr == 'nan': ip_addr = ''
        
        mac_addr = str(row.get('Primary MAC Address', '')).strip()
        if mac_addr == 'nan': mac_addr = ''
        
        owner = str(row.get('Primary Owner', '')).strip()
        if owner == 'nan': owner = ''
        
        os_type = str(row.get('OS Type', '')).strip()
        if os_type == 'nan': os_type = ''
        
        # Location logic
        loc = str(row.get('last_location', '')).strip()
        if loc in ['nan', 'None', '']: 
            loc = str(row.get('Location', '')).strip()
        if loc == 'nan': loc = ''
        
        # SQL
        if db.mode == "CLOUD":
            query = """
            INSERT INTO kpu_enterprise_computing_machines 
            (asset_id, name, ip_address, mac_address, owner, os_type, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (asset_id, name, ip_addr, mac_addr, owner, os_type, loc))
        else:
             # Local SQLite
            query = """
            INSERT INTO kpu_enterprise_computing_machines 
            (asset_id, name, ip_address, mac_address, owner, os_type, location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(query, (asset_id, name, ip_addr, mac_addr, owner, os_type, loc))
            
        count += 1
        
    conn.commit()
    conn.close()
            
    print(f"✅ Imported {count} machines into kpu_enterprise_computing_machines.")

if __name__ == "__main__":
    import_data()

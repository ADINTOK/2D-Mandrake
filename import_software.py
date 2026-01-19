
import pandas as pd
from database_manager import DatabaseManager
import streamlit as st

def import_data():
    print("Starting import...")
    csv_path = r"C:\Users\Anand\Downloads\KPU_MasterAsset_List - Layer7List.csv"
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    db = DatabaseManager()
    
    # Expected columns: Asset_ID,Name,Manufacturer,MFA Enabled
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
        if asset_id == 'nan': asset_id = ''
        
        name = str(row.get('Name', '')).strip()
        
        manufacturer = str(row.get('Manufacturer', '')).strip()
        if manufacturer == 'nan': manufacturer = ''
        
        mfa = str(row.get('MFA Enabled', '')).strip()
        if mfa == 'nan': mfa = ''

        if not name: continue # Skip empty rows

        # SQL
        if db.mode == "CLOUD":
            query = """
            INSERT INTO kpu_enterprise_software (asset_id, name, manufacturer, mfa_enabled)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (asset_id, name, manufacturer, mfa))
        else:
             # Local SQLite
            query = """
            INSERT INTO kpu_enterprise_software (asset_id, name, manufacturer, mfa_enabled)
            VALUES (?, ?, ?, ?)
            """
            cursor.execute(query, (asset_id, name, manufacturer, mfa))
            
        count += 1
        
    conn.commit()
    conn.close()
            
    print(f"✅ Imported {count} records into kpu_enterprise_software.")

if __name__ == "__main__":
    import_data()

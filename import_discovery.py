import csv
import sys
import os
from database_manager import DatabaseManager

# =============================================================================
# Script: Discovery Import
# =============================================================================
# Usage: python import_discovery.py <path_to_csv>
# CSV Format: ip_address, mac_address, hostname, os_type, location
# Upsert Logic: specific to Computing Machines
# =============================================================================

def import_csv(file_path):
    print(f"--- Starting Import from {file_path} ---")
    
    if not os.path.exists(file_path):
        print("Error: File not found.")
        return

    db = DatabaseManager()
    
    count_new = 0
    count_upd = 0
    
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            # Normalize headers if needed (strip spaces)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                ip = row.get("ip_address", "").strip()
                mac = row.get("mac_address", "").strip()
                host = row.get("hostname", "").strip()
                os_type = row.get("os_type", "").strip()
                loc = row.get("location", "Unknown Location")
                
                if not host or not ip:
                    print(f"Skipping row missing host/ip: {row}")
                    continue
                
                # Check exist by MAC or IP
                existing = None
                if mac:
                    res = db.execute(f"SELECT id FROM kpu_enterprise_computing_machines WHERE mac_address='{mac}'", fetch=True)
                    if res: existing = res[0]
                
                if not existing and ip:
                    res = db.execute(f"SELECT id FROM kpu_enterprise_computing_machines WHERE ip_address='{ip}'", fetch=True)
                    if res: existing = res[0]
                    
                if existing:
                    # UPDATE
                    eid = existing['id']
                    print(f"Updating {host} (ID: {eid})...")
                    if db.mode == "CLOUD":
                        sql = "UPDATE kpu_enterprise_computing_machines SET name=%s, ip_address=%s, mac_address=%s, os_type=%s, location=%s WHERE id=%s"
                        db.execute(sql, (host, ip, mac, os_type, loc, eid))
                    else:
                        sql = "UPDATE kpu_enterprise_computing_machines SET name=?, ip_address=?, mac_address=?, os_type=?, location=? WHERE id=?"
                        db.execute(sql, (host, ip, mac, os_type, loc, eid))
                    count_upd += 1
                else:
                    # INSERT
                    print(f"Creating New Asset: {host}...")
                    if db.mode == "CLOUD":
                        sql = "INSERT INTO kpu_enterprise_computing_machines (name, ip_address, mac_address, os_type, location, created_at) VALUES (%s, %s, %s, %s, %s, NOW())"
                        db.execute(sql, (host, ip, mac, os_type, loc))
                    else:
                        sql = "INSERT INTO kpu_enterprise_computing_machines (name, ip_address, mac_address, os_type, location, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))"
                        db.execute(sql, (host, ip, mac, os_type, loc))
                    count_new += 1
                    
        print(f"--- Import Complete ---")
        print(f"Created: {count_new}")
        print(f"Updated: {count_upd}")
        
    except Exception as e:
        print(f"Import Failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_discovery.py <csv_file>")
        # Create Dummy CSV for ease of testing
        dummy_csv = "discovery_sample.csv"
        with open(dummy_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ip_address", "mac_address", "hostname", "os_type", "location"])
            writer.writerow(["192.168.1.50", "00:11:22:33:44:55", "DISC-SRV-01", "Ubuntu 22.04", "Server Room"])
            writer.writerow(["192.168.1.101", "AA:BB:CC:DD:EE:FF", "DISC-PC-HR", "Windows 11", "HR Office"])
        print(f"Created sample file '{dummy_csv}'. Run again with this file.")
    else:
        import_csv(sys.argv[1])

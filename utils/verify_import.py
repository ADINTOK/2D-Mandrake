
import sys
import os
import streamlit as st

# Add parent directory to path to import database_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_manager import DatabaseManager

try:
    db = DatabaseManager()
    
    # Check Machines
    res_machines = db.execute("SELECT COUNT(*) as tr_count FROM kpu_enterprise_computing_machines", fetch=True)
    count_machines = res_machines[0]['tr_count'] if res_machines else 0
    
    # Check Software
    res_software = db.execute("SELECT COUNT(*) as tr_count FROM kpu_enterprise_software", fetch=True)
    count_software = res_software[0]['tr_count'] if res_software else 0
    
    output = f"""
VERIFICATION RESULT:
--------------------
Machines: {count_machines}
Software: {count_software}
    """
    print(output)
    
    with open("utils/verification_result.txt", "w") as f:
        f.write(output)

except Exception as e:
    err = f"VERIFICATION_ERROR: {e}"
    print(err)
    with open("utils/verification_result.txt", "w") as f:
        f.write(err)

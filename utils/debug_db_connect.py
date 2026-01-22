
import sys
import os
import toml

# Add parent to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_manager import DatabaseManager

# Mock Streamlit secrets if needed or just pass to manager
# DatabaseManager needs st.secrets for some internals if not fully overridden
# But we can try to patch st.secrets
import streamlit as st

print("LOADING SECRETS...")
try:
    with open(".streamlit/secrets.toml", "r") as f:
        secrets = toml.load(f)
        # Patch st.secrets shim
        st.secrets = secrets
except Exception as e:
    print(f"Failed to load secrets: {e}")
    sys.exit(1)

print("INITIALIZING DB MANAGER...")
try:
    # Pass secrets explicitly too
    db = DatabaseManager(secrets_override=secrets)
except Exception as e:
    print(f"Init Failed: {e}")
    # Continue anyway to test methods 
    pass

print("\n--- TEST PRIMARY ---")
try:
    if "mysql" in secrets:
        print(f"Host: {secrets['mysql'].get('host')}")
        tables = db.get_tables("PRIMARY")
        print(f"RESULT: Found {len(tables)} tables.")
        print(tables)
    else:
        print("No [mysql] secret")
except Exception as e:
    print(f"ERROR PRIMARY: {e}")
    import traceback
    traceback.print_exc()

print("\n--- TEST SECONDARY ---")
try:
    if "mysql_backup" in secrets:
        print(f"Host: {secrets['mysql_backup'].get('host')}")
        tables = db.get_tables("SECONDARY")
        print(f"RESULT: Found {len(tables)} tables.")
        print(tables)
    else:
        print("No [mysql_backup] secret")
except Exception as e:
    print(f"ERROR SECONDARY: {e}")
    import traceback
    traceback.print_exc()

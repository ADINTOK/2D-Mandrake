
import mysql.connector
import os
import sys
import toml
import socket

# Add utils to path
sys.path.append(os.getcwd())
from utils.sshtunnel_helper import SSHTunnel

def test_connectivity():
    secrets_path = ".streamlit/secrets.toml"
    if not os.path.exists(secrets_path):
        print("Error: .streamlit/secrets.toml not found")
        return

    secrets = toml.load(secrets_path)
    
    def connect_via_ssh(config, ssh_cfg):
        tunnel = None
        try:
            print(f"--- Testing SSH Tunnel to {ssh_cfg['host']} ---")
            tunnel = SSHTunnel(
                ssh_host=ssh_cfg['host'],
                ssh_user=ssh_cfg['user'],
                ssh_password=ssh_cfg['password'],
                remote_bind_address=('127.0.0.1', 3306),
                ssh_port=ssh_cfg.get('port', 22)
            )
            local_port = tunnel.start()
            print(f"Tunnel established on port {local_port}")
            
            print(f"--- Testing MySQL Connection via Tunnel to {config['database']} ---")
            conn = mysql.connector.connect(
                host='127.0.0.1',
                user=config['user'],
                password=config['password'],
                database=config['database'],
                port=local_port,
                connection_timeout=5
            )
            if conn.is_connected():
                print("SUCCESS: Connected to Cloud (Primary via SSH)")
                conn.close()
            tunnel.stop()
        except Exception as e:
            print(f"FAILED: SSH/Primary Connection: {e}")
            if tunnel: tunnel.stop()

    def connect_direct(config, label):
        try:
            print(f"--- Testing Direct MySQL Connection to {config['host']} ({label}) ---")
            conn = mysql.connector.connect(
                host=config['host'],
                user=config['user'],
                password=config['password'],
                database=config['database'],
                port=config.get('port', 3306),
                connection_timeout=5
            )
            if conn.is_connected():
                print(f"SUCCESS: Connected to Cloud ({label})")
                conn.close()
        except Exception as e:
            print(f"FAILED: {label} Connection: {e}")

    # Test Primary (with SSH)
    if "mysql" in secrets and "ssh" in secrets:
        connect_via_ssh(secrets["mysql"], secrets["ssh"])
    
    # Test Backup (Direct)
    if "mysql_backup" in secrets:
        connect_direct(secrets["mysql_backup"], "Backup")

if __name__ == "__main__":
    test_connectivity()

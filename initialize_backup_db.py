import mysql.connector
import streamlit as st

# =============================================================================
# Backup Database Initialization
# =============================================================================
# Purpose: Initialize the Secondary Cloud Database (dubaytech_db)
# Features: 
# - Connects using [mysql_backup] secrets
# - Creates all tables (Assets, Tickets, ITIL V2 tables)
# - Adds detailed SQL COMMENTs to Tables and Columns
# =============================================================================

def get_backup_connection():
    if "mysql_backup" in st.secrets:
        s = st.secrets["mysql_backup"]
        print(f"Connecting to Backup DB at {s['host']}...")
        return mysql.connector.connect(
            host=s["host"],
            user=s["user"],
            password=s["password"],
            database=s["database"],
            port=s.get("port", 3306)
        )
    else:
        print("Error: [mysql_backup] not found in secrets.")
        return None

def setup_backup_db():
    try:
        conn = get_backup_connection()
        if not conn: return
        cursor = conn.cursor()
        
        print("--- initializing Backup Schema ---")
        
        # 1. Assets Table
        print("Creating 'assets'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique Identifier',
            parent_id INT COMMENT 'Parent Asset ID for hierarchy',
            name VARCHAR(255) NOT NULL COMMENT 'Display Name of the Asset',
            type VARCHAR(50) COMMENT 'Asset Type (e.g., System, Group, Asset)',
            description TEXT COMMENT 'Detailed description',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation Timestamp',
            CONSTRAINT fk_assets_parent FOREIGN KEY (parent_id) REFERENCES assets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB COMMENT='Core Asset Inventory Table';
        """)

        # 2. Tickets Table (V2 Schema)
        print("Creating 'tickets'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Ticket Number',
            asset_id INT NOT NULL COMMENT 'Linked Asset ID',
            ticket_type VARCHAR(50) COMMENT 'Incident, Request, Change, Problem',
            title VARCHAR(255) COMMENT 'Summary of the issue',
            description TEXT COMMENT 'Detailed explanation',
            status VARCHAR(50) DEFAULT 'Open' COMMENT 'Current State (Open, Closed, etc.)',
            priority VARCHAR(50) COMMENT 'Urgency (Critical, High, Medium, Low)',
            logged_by VARCHAR(100) COMMENT 'User who created the ticket',
            related_type VARCHAR(50) DEFAULT 'asset' COMMENT 'Polymorphic type (asset, software)',
            due_date DATETIME COMMENT 'SLA Deadline',
            problem_id INT COMMENT 'Linked Problem Record ID',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_asset_id (asset_id),
            CONSTRAINT fk_tickets_asset FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB COMMENT='Central Ticket Registry';
        """)

        # 3. ITIL V2 Tables
        
        # Knowledge Base
        print("Creating 'knowledge_articles'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_articles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            content TEXT COMMENT 'Markdown Content',
            category VARCHAR(100),
            tags VARCHAR(255),
            author VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB COMMENT='Knowledge Base Articles';
        """)

        # SLA Policies
        print("Creating 'sla_policies'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sla_policies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            priority VARCHAR(50) UNIQUE COMMENT 'Priority Level',
            response_time_minutes INT COMMENT 'Target Response Time',
            resolution_time_minutes INT COMMENT 'Target Resolution Time',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB COMMENT='SLA Definitions';
        """)
        
        # Problems
        print("Creating 'problems'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            root_cause_analysis TEXT COMMENT 'RCA Findings',
            status VARCHAR(50) DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB COMMENT='Problem Management Records';
        """)
        
        # Ticket FK for Problems (Alter if needed, or create fresh)
        # Note: tickets table creation defined problem_id but without FK constraint initially if problem didn't exist.
        # Since we create tables in order, we can add constraint now or alter.
        # Let's add constraint to tickets now that problems exists
        try:
             cursor.execute("ALTER TABLE tickets ADD CONSTRAINT fk_ticket_problem FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE SET NULL")
        except: pass

        # Software Licenses
        print("Creating 'software_licenses'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS software_licenses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            software_asset_id INT NOT NULL COMMENT 'Link to Enterprise Software Asset',
            license_key VARCHAR(255),
            vendor VARCHAR(255),
            total_seats INT DEFAULT 0 COMMENT 'Total Purchased Seats',
            used_seats INT DEFAULT 0 COMMENT 'Currently Assigned Seats',
            expiration_date DATE COMMENT 'License Expiry',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB COMMENT='Software License Tracking';
        """)
        
        # Change Approvals
        print("Creating 'change_approvals'...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_approvals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticket_id INT NOT NULL,
            approver_role VARCHAR(100),
            status VARCHAR(50) DEFAULT 'Pending',
            comments TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_approvals_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB COMMENT='CAB Approval Workflow';
        """)
        
        # 4. KPU Asset Tables (Business Services, Enterprise Assets etc)
        # We need these for the app to function fully on backup.
        # Simplified creation for brevity - critical for app startup
        
        print("Creating hierarchy tables...")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_business_services_level1 (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), description TEXT, owner VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_business_services_level2 (id INT AUTO_INCREMENT PRIMARY KEY, business_service_level1_id INT, name VARCHAR(255), description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_technical_services (id INT AUTO_INCREMENT PRIMARY KEY, business_service_level2_id INT, name VARCHAR(255), description TEXT, sla_level VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_enterprise_assets (id INT AUTO_INCREMENT PRIMARY KEY, technical_service_id INT, name VARCHAR(255), asset_type VARCHAR(100), location VARCHAR(100), status VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_component_assets (id INT AUTO_INCREMENT PRIMARY KEY, enterprise_asset_id INT, name VARCHAR(255), component_type VARCHAR(100), version VARCHAR(50), description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_enterprise_software (id INT AUTO_INCREMENT PRIMARY KEY, asset_id VARCHAR(255), name VARCHAR(255), manufacturer VARCHAR(255), mfa_enabled VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (id INT AUTO_INCREMENT PRIMARY KEY, asset_id VARCHAR(255), name VARCHAR(255), ip_address VARCHAR(50), mac_address VARCHAR(50), owner VARCHAR(255), os_type VARCHAR(100), location VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        
        # 5. ISO/NIST
        print("Creating Controls...")
        cursor.execute("CREATE TABLE IF NOT EXISTS iso_controls (id VARCHAR(10) PRIMARY KEY, theme VARCHAR(50), description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")
        cursor.execute("CREATE TABLE IF NOT EXISTS nist_controls (id VARCHAR(10) PRIMARY KEY, function VARCHAR(50), category VARCHAR(100), description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;")

        # Mappings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asset_controls (
                id INT AUTO_INCREMENT PRIMARY KEY, 
                asset_id INT NOT NULL, 
                related_type VARCHAR(50) DEFAULT 'asset',
                control_id VARCHAR(10) NOT NULL, 
                status VARCHAR(50), 
                notes TEXT, 
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;
        """)

        conn.commit()
        print("✅ Backup Database Initialized Successfully!")
        conn.close()

    except Exception as e:
        print(f"❌ Initialization Failed: {e}")

if __name__ == "__main__":
    setup_backup_db()

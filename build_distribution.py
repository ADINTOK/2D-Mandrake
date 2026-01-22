import os
import zipfile
import datetime

def build_slim_zip():
    project_name = "2D_Mandrake"
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    zip_filename = f"{project_name}_Slim_{date_str}.zip"
    
    # Exclusion Patterns (Folders and Files)
    EXCLUDED_DIRS = {
        'venv', 
        '__pycache__', 
        '.git', 
        '.streamlit', 
        '__MACOSX'
    }
    
    EXCLUDED_FILES = {
        '.defender_checked',
        '.setup_complete',
        'local_cache.db',
        'local_data.db',
        '.DS_Store'
    }
    
    EXCLUDED_EXTENSIONS = {
        '.zip',
        '.pyc'
    }

    print(f"--- Building Slim Distribution: {zip_filename} ---")
    
    # Remove existing zip if it exists
    if os.path.exists(zip_filename):
        try:
            os.remove(zip_filename)
            print(f"[!] Removed existing {zip_filename}")
        except OSError as e:
            print(f"[-] Error removing existing file: {e}")
            return False

    cwd = os.getcwd()
    file_count = 0
    
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            print("[*] Gathering files...")
            
            for root, dirs, files in os.walk(cwd):
                # 1. Prune Excluded Directories in-place
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, cwd)
                    
                    # 2. Check File Exclusions
                    if file in EXCLUDED_FILES:
                        continue
                        
                    _, ext = os.path.splitext(file)
                    if ext in EXCLUDED_EXTENSIONS:
                        continue
                        
                    # 3. Add to Zip
                    zipf.write(file_path, rel_path)
                    file_count += 1
                    
        size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
        print(f"[SUCCESS] Build Complete!")
        print(f"[+] Files zipped: {file_count}")
        print(f"[+] Zip Size: {size_mb:.2f} MB")
        print(f"[+] Path: {os.path.abspath(zip_filename)}")
        return True

    except Exception as e:
        print(f"[-] Build Failed: {e}")
        return False

if __name__ == "__main__":
    build_slim_zip()

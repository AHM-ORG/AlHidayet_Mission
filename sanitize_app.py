import os
import shutil

def sanitize_file(file_path):
    backup_path = file_path + '.bak'
    
    # Create a backup first
    shutil.copy2(file_path, backup_path)
    print(f"Backup created at: {backup_path}")
    
    # Read raw bytes
    with open(file_path, 'rb') as f:
        content = f.read()
        
    original_size = len(content)
    
    # Remove null bytes
    cleaned_content = content.replace(b'\x00', b'')
    new_size = len(cleaned_content)
    
    # Write the cleaned content back
    with open(file_path, 'wb') as f:
        f.write(cleaned_content)
        
    removed_bytes = original_size - new_size
    if removed_bytes > 0:
        print(f"Success! Removed {removed_bytes} null byte(s) from {file_path}.")
    else:
        print(f"No null bytes found in {file_path}.")

if __name__ == "__main__":
    sanitize_file('app.py')

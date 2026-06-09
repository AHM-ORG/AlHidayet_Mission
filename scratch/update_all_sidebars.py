import glob
import os
import re

def main():
    dashboard_path = 'templates/dashboard.html'
    if not os.path.exists(dashboard_path):
        print("Error: templates/dashboard.html not found.")
        return
        
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        dash_content = f.read()
        
    # Extract master sidebar block
    match = re.search(r'(<aside\s+class="sidebar"[^>]*>.*?</aside>)', dash_content, re.DOTALL)
    if not match:
        print("Error: Could not find sidebar block in dashboard.html")
        return
        
    master_sidebar = match.group(1)
    
    # Add failsafe logo fallback
    master_sidebar = master_sidebar.replace(
        'src="{{ logo_url }}"',
        'src="{{ logo_url or url_for(\'static\', filename=\'images/logo.png\') }}"'
    )
    
    print("Master sidebar extracted successfully.")
    
    # Scan and update all html files
    html_files = glob.glob('templates/**/*.html', recursive=True)
    updated_count = 0
    
    for file_path in html_files:
        # Skip dashboard.html itself, but we can write to it if needed
        # We will update dashboard.html as well to use the fallback logo
        
        content = ""
        encoding = 'utf-8'
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='utf-16') as f:
                    content = f.read()
                encoding = 'utf-16'
            except Exception as e:
                print(f"Skipping {file_path} due to decode error: {e}")
                continue
                
        # Find if this file has a sidebar
        if '<aside class="sidebar"' in content:
            # Replace the old sidebar block with the master sidebar
            new_content, count = re.subn(r'<aside\s+class="sidebar"[^>]*>.*?</aside>', master_sidebar, content, flags=re.DOTALL)
            if count > 0:
                with open(file_path, 'w', encoding=encoding) as f:
                    f.write(new_content)
                print(f"Updated sidebar in: {file_path} ({encoding})")
                updated_count += 1
                
    print(f"Completed! Synchronized sidebars in {updated_count} files.")

if __name__ == '__main__':
    main()

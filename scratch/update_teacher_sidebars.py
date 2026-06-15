import glob
import os

def read_file(file_path):
    # Try reading as utf-8, then utf-16, and fallback
    encodings = ['utf-8', 'utf-16', 'utf-8-sig', 'utf-16-le', 'utf-16-be']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
            return content, enc
        except UnicodeError:
            continue
    # final fallback
    with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
        content = f.read()
    return content, 'latin-1'

def main():
    templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    html_files = glob.glob(os.path.join(templates_dir, "**", "*.html"), recursive=True)
    
    target_link = '<a href="/teacher/attendance-leaves" class="sidebar-item {% if request.path == \'/teacher/attendance-leaves\' %}active{% endif %}"><i data-lucide="calendar-days"></i> Attendance & Leaves</a>'
    target_link_alt = '<a href="/teacher/attendance-leaves" class="sidebar-item {% if request.path == \'/teacher/attendance-leaves\' %}active{% endif %}"><i data-lucide="calendar-days"></i> Attendance &amp; Leaves</a>'
    
    new_link = '<a href="/teacher/edit-info" class="sidebar-item {% if request.path == \'/teacher/edit-info\' %}active{% endif %}"><i data-lucide="user-cog"></i> Edit Profile</a>'
    
    updated_count = 0
    for file_path in html_files:
        if "edit_info.html" in file_path:
            continue
            
        content, encoding = read_file(file_path)
            
        if 'href="/teacher/edit-info"' in content or "href='/teacher/edit-info'" in content:
            print(f"Skipping {os.path.basename(file_path)}, already has teacher edit-info sidebar link.")
            continue
            
        modified = False
        
        # Check target_link
        if target_link in content:
            content = content.replace(target_link, f"{target_link}\n                {new_link}")
            modified = True
        elif target_link_alt in content:
            content = content.replace(target_link_alt, f"{target_link_alt}\n                {new_link}")
            modified = True
        else:
            # Try replacing with generic double/single quote variation
            # e.g., using " instead of ' in request.path comparison
            target_link_double = target_link.replace("'/teacher/attendance-leaves'", '"/teacher/attendance-leaves"')
            if target_link_double in content:
                content = content.replace(target_link_double, f"{target_link_double}\n                {new_link}")
                modified = True
            
        if modified:
            with open(file_path, 'w', encoding=encoding, newline='') as f:
                f.write(content)
            print(f"Updated sidebar in: {os.path.basename(file_path)} (Encoding: {encoding})")
            updated_count += 1
            
    print(f"Done! Updated {updated_count} files.")

if __name__ == "__main__":
    main()

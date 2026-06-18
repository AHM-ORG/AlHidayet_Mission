import glob
import os

def update_sidebars():
    print("Scanning templates to inject 'Guardian Meetings' sidebar items with encoding protection...")
    files = glob.glob('templates/**/*.html', recursive=True)
    updated_count = 0
    
    for f in files:
        if os.path.basename(f) in ['guardian_meetings.html', 'guardian_meeting_attendance.html']:
            continue
            
        content = ""
        encoding = 'utf-8'
        
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
        except UnicodeDecodeError:
            try:
                with open(f, 'r', encoding='utf-16') as file:
                    content = file.read()
                encoding = 'utf-16'
            except Exception as e:
                print(f" [!] Failed to decode {f} with utf-8/utf-16: {e}")
                continue
                
        if '<aside class="sidebar' not in content:
            continue
            
        modified = False
        
        # 1. Admin Sidebar Injection: Under 'Academics' Label
        admin_link = '<a href="/admin/guardian-meetings" class="sidebar-item {% if request.path == \'/admin/guardian-meetings\' %}active{% endif %}"><i data-lucide="presentation"></i> Guardian Meetings</a>'
        if 'Academics</div>' in content and admin_link not in content:
            content = content.replace(
                '<div class="sidebar-label">Academics</div>',
                '<div class="sidebar-label">Academics</div>\n                ' + admin_link
            )
            modified = True
            
        # 2. Teacher Sidebar Injection: Under 'Academic Tools' Label
        teacher_link = '<a href="/admin/guardian-meetings" class="sidebar-item {% if request.path == \'/admin/guardian-meetings\' %}active{% endif %}"><i data-lucide="presentation"></i> Guardian Meetings</a>'
        if 'Academic Tools</div>' in content and teacher_link not in content:
            content = content.replace(
                '<div class="sidebar-label">Academic Tools</div>',
                '<div class="sidebar-label">Academic Tools</div>\n                ' + teacher_link
            )
            modified = True
            
        if modified:
            with open(f, 'w', encoding=encoding) as file:
                file.write(content)
            print(f" [+] Updated sidebar in ({encoding}): {f}")
            updated_count += 1
            
    print(f"Sidebar update completed! Modified {updated_count} files.")

if __name__ == '__main__':
    update_sidebars()

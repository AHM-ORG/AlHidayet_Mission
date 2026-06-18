import os

def run_update():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, 'templates')
    
    count = 0
    for root, dirs, files in os.walk(templates_dir):
        for name in files:
            if name.endswith('.html'):
                f = os.path.join(root, name)
                content = None
                used_encoding = 'utf-8'
                
                # Try UTF-8
                try:
                    with open(f, 'r', encoding='utf-8') as file:
                        content = file.read()
                except UnicodeDecodeError:
                    # Try UTF-16
                    try:
                        with open(f, 'r', encoding='utf-16') as file:
                            content = file.read()
                        used_encoding = 'utf-16'
                    except Exception as e:
                        print(f"Skipped {f} due to encoding error: {e}")
                        continue
                except Exception as e:
                    print(f"Skipped {f} due to error: {e}")
                    continue
                    
                # Check for certificates
                has_cert = '/admin/manage-certificates' in content
                has_teacher_cert = '/teacher/my-certificates' in content
                has_student_cert = '/student/my-certificates' in content
                has_mc = '/admin/managing-committee' in content
                has_teacher_complaints = '/teacher/complaints' in content
                
                lines = content.splitlines()
                new_lines = []
                need_update = False
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if '/admin/id-card' in line and 'class="sidebar-item' in line:
                        if 'Id Card' in line and not has_cert:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/admin/manage-certificates" class="sidebar-item {{% if request.path == \'/admin/manage-certificates\' %}}active{{% endif %}}"><i data-lucide="award"></i> Certificates</a>')
                            need_update = True
                        elif 'ID Cards' in line and not has_teacher_cert:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/teacher/my-certificates" class="sidebar-item {{% if request.path == \'/teacher/my-certificates\' %}}active{{% endif %}}"><i data-lucide="award"></i> My Certificates</a>')
                            need_update = True
                        elif 'My ID Card' in line and not has_student_cert:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/student/my-certificates" class="sidebar-item {{% if request.path == \'/student/my-certificates\' %}}active{{% endif %}}"><i data-lucide="award"></i> My Certificates</a>')
                            need_update = True
                    if '/admin/applications' in line and 'class="sidebar-item' in line and not has_mc:
                        indent = len(line) - len(line.lstrip())
                        spacing = ' ' * indent
                        new_lines.append(f'{spacing}<a href="/admin/managing-committee" class="sidebar-item {{% if request.path == \'/admin/managing-committee\' %}}active{{% endif %}}"><i data-lucide="contact"></i> Managing Committee</a>')
                        need_update = True
                    if '/admin/leaves' in line and 'class="sidebar-item' in line:
                        # Look ahead for next 3 lines to see if it already has charts
                        has_next_charts = False
                        for next_line in lines[i+1:i+4]:
                            if '/admin/attendance-charts' in next_line:
                                has_next_charts = True
                                break
                        if not has_next_charts:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/admin/attendance-charts" class="sidebar-item {{% if request.path == \'/admin/attendance-charts\' %}}active{{% endif %}}"><i data-lucide="bar-chart-3"></i> Attendance Charts</a>')
                            need_update = True
                    if '/teacher/attendance-leaves' in line and 'class="sidebar-item' in line:
                        # Look ahead for next 3 lines to see if it already has charts
                        has_next_charts = False
                        for next_line in lines[i+1:i+4]:
                            if '/admin/attendance-charts' in next_line:
                                has_next_charts = True
                                break
                        if not has_next_charts:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/admin/attendance-charts" class="sidebar-item {{% if request.path == \'/admin/attendance-charts\' %}}active{{% endif %}}"><i data-lucide="bar-chart-3"></i> Attendance Charts</a>')
                            need_update = True
                        if not has_teacher_complaints:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/teacher/complaints" class="sidebar-item {{% if request.path == \'/teacher/complaints\' %}}active{{% endif %}}"><i data-lucide="message-square"></i> Complaints Box</a>')
                            need_update = True
                    if '/routine' in line and 'class="sidebar-item' in line and 'Class Routine' in line and 'My Class Routine' not in line:
                        # Look ahead for next 3 lines to see if it already has question papers
                        has_next_qp = False
                        for next_line in lines[i+1:i+4]:
                            if '/admin/question-papers' in next_line:
                                has_next_qp = True
                                break
                        if not has_next_qp:
                            indent = len(line) - len(line.lstrip())
                            spacing = ' ' * indent
                            new_lines.append(f'{spacing}<a href="/admin/question-papers" class="sidebar-item {{% if request.path == \'/admin/question-papers\' %}}active{{% endif %}}"><i data-lucide="file-text"></i> Question Paper Bank</a>')
                            need_update = True
                            
                if need_update:
                    content = '\n'.join(new_lines)
                    with open(f, 'w', encoding=used_encoding) as file:
                        file.write(content)
                    print('Updated sidebar in', f)
                    count += 1
    print(f'Successfully updated sidebars in {count} files.')

if __name__ == '__main__':
    run_update()

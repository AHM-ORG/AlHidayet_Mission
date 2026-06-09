<USER_REQUEST>
sorry python file, import pandas as pd
from jinja2 import Template
import re
import os

# 1. THE HTML TEMPLATE
html_template_string = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Annual Results 2025</title>
    <style>
        @page { size: A4; margin: 0; }
        body { margin: 0; padding: 0; font-family: 'Times New Roman', Times, serif; background-color: #FFFFF0; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
        .page { width: 210mm; height: 296mm; position: relative; padding: 5mm; box-sizing: border-box; overflow: hidden; page-break-after: always; }
        .watermark { position: absolute; top: 25%; left: 15%; width: 70%; height: 50%; background-image: url('https://i.ibb.co/Jjk1qNkj/logo-1-removebg-preview.png'); background-repeat: no-repeat; background-position: center; background-size: contain; opacity: 0.08; z-index: -1; }
        .border-container { border: 3px double black; height: 100%; padding: 8px; box-sizing: border-box; display: flex; flex-direction: column; justify-content: space-between; }
        .header { text-align: center; position: relative; margin-bottom: 5px; border-bottom: 2px solid #d60000; padding-bottom: 5px; flex-shrink: 0; }
        .logo { width: 75px; position: absolute; top: 0; }
        .logo-left { left: 5px; }
        .logo-right { right: 5px; }
        h1 { color: #d60000; font-size: 28pt; margin: 0; font-weight: 900; line-height: 1; text-shadow: 1px 1px 0px #eee; }
        .branch { color: #333; font-size: 12pt; font-weight: bold; margin: 2px 0; letter-spacing: 1px; }
        .addr { font-size: 10pt; margin: 2px 0; color: #444; }
        .title { background-color: #d60000; color: white; font-weight: bold; font-size: 15pt; padding: 4px 30px; border-radius: 20px; display: inline-block; margin-top: 5px; text-decoration: none; }
        table { width: 100%; border-collapse: collapse; font-size: 10.5pt; margin-bottom: 5px; }
        td, th { border: 1px solid #444; padding: 6px 3px; text
<truncated 19832 bytes>
_marks'] = final_max_marks
        
        if s['max_marks'] > 0:
            s['percentage'] = round((s['total_obtained'] / s['max_marks']) * 100, 2)
        else:
            s['percentage'] = 0
            
        s['overall_grade'] = calculate_overall_grade(s['percentage'])
        
        students_list.append(s)

    # --- RANK ---
    students_list.sort(key=lambda x: x['total_obtained'], reverse=True)
    current_rank = 1
    for i, student in enumerate(students_list):
        if i > 0 and student['total_obtained'] == students_list[i-1]['total_obtained']:
            student['rank'] = students_list[i-1]['rank']
        else:
            student['rank'] = current_rank
        current_rank += 1
        
    try:
        students_list.sort(key=lambda x: int(x['roll']) if str(x['roll']).isdigit() else x['roll'])
    except:
        pass 

    # 4. RENDER
    template = Template(html_template_string)
    output_html = template.render(students=students_list)

    with open("final_report_cards_v7.html", "w", encoding="utf-8") as f:
        f.write(output_html)

    print("Success! Generated final_report_cards_v7.html")

if __name__ == "__main__":
    process_data("student.xlsx") note : here will not given any excel, all info added by admin and assigned teacher, create a format to input marks properly, and subjects may varrey by classes
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-06-03T14:24:29+05:30.

The user's current state is as follows:
Active Document: d:\AHM\AHM-Web\app.py (LANGUAGE_PYTHON)
Cursor is on line: 4290
Other open documents:
- d:\AHM\AHM-Web\scratch\test_fee_documents.py (LANGUAGE_PYTHON)
- d:\AHM\AHM-Web\templates\admin\marksheet.html (LANGUAGE_HTML)
- d:\AHM\AHM-Web\templates\admin\academics_setting.html (LANGUAGE_HTML)
- d:\AHM\AHM-Web\templates\index.html (LANGUAGE_HTML)
- d:\AHM\AHM-Web\app.py (LANGUAGE_PYTHON)
Running terminal commands:
- & d:/AHM/AHM-Web/.venv/Scripts/python.exe d:/AHM/AHM-Web/app.py (in d:\AHM\AHM-Web, running for 16m11s)
</ADDITIONAL_METADATA>
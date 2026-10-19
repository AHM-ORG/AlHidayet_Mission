import pandas as pd
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
        td, th { border: 1px solid #444; padding: 6px 3px; text-align: center; }
        .info-tbl { margin-bottom: 10px; }
        .info-tbl td { text-align: left; padding: 6px; border: 1px solid #000; }
        .lbl-name, .lbl-class, .lbl-roll, .lbl-sec { background-color: #1a237e; color: white; text-align: center !important; }
        .lbl-name { width: 15%; } .lbl-class { width: 10%; } .lbl-roll { width: 8%; } .lbl-sec { width: 8%; }
        .val { font-family: 'Times New Roman', serif; font-weight: bold; font-size: 11pt; padding-left: 5px; }
        .green { color: #006400; font-weight: 900; text-transform: uppercase; }
        .th-main { background-color: #333; color: white; font-weight: bold; }
        .th-u1 { background-color: #cce5ff; color: black; }
        .bg-unit1 { background-color: #f0f8ff; }
        .th-u2 { background-color: #d4edda; color: black; }
        .bg-unit2 { background-color: #f8fff9; }
        .th-final { background-color: #f8d7da; color: black; }
        .bg-final { background-color: #fff5f6; }
        .th-total { background-color: #fff3cd; color: black; }
        .bg-total { background-color: #fff9db; font-weight: bold; }
        .bg-grade { background-color: white; font-weight: bold; }
        .sub-tot { font-weight: bold; background-color: rgba(0, 0, 0, 0.05); }
        .footer-table { border: none; margin-top: 10px; flex-grow: 1; }
        .footer-table td { border: none; vertical-align: top; padding: 5px; }
        .col-left { width: 55%; padding-right: 15px !important; }
        .col-right { width: 45%; }
        .sub-table { border: 2px solid black; height: 100%; }
        .sub-table td, .sub-table th { border: 1px solid black; padding: 5px; }
        .sub-header { background-color: #444; color: white; padding: 5px; font-weight: bold; border: 1px solid black; }
        .summary-box { margin-top: 15px; }
        .stamp-container { position: relative; height: auto; padding: 10px; display: flex; align-items: center; justify-content: center; flex-direction: column; border: 2px dashed #ccc; border-radius: 10px; margin-top: 15px; background-color: #fcfcfc; }
        .passed { color: #2e7d32; font-size: 32pt; font-weight: 900; font-family: 'Arial Black', sans-serif; border: 4px solid #2e7d32; padding: 5px 20px; transform: rotate(-8deg); opacity: 0.9; background: rgba(255, 255, 255, 0.95); margin-top: 5px; z-index: 10; }
        .sig-row { display: flex; justify-content: space-between; margin-top: 20px; margin-bottom: 5px; flex-shrink: 0; align-items: flex-end; }
        .sig-box { width: 30%; border-top: 1px solid black; text-align: center; font-size: 11pt; font-weight: bold; padding-top: 5px; position: relative; height: 40px; }
        .tic-img { position: absolute; bottom: 60px; left: 50%; transform: translateX(-50%); width: 150px; z-index: 5; }
    </style>
</head>
<body>
    {% for s in students %}
    <div class="page">
        <div class="watermark"></div>
        <div class="border-container">
            <div>
                <div class="header">
                    <img src="https://i.ibb.co/Jjk1qNkj/logo-1-removebg-preview.png" class="logo logo-left">
                    <img src="https://i.ibb.co/Jjk1qNkj/logo-1-removebg-preview.png" class="logo logo-right">
                    <h1>AL - HIDAYET MISSION</h1>
                    <div class="branch">(BHOGRAM BRANCH)</div>
                    <div class="addr">BHOGRAM, P.O – BHOGRAM, P.S – HEMTABAD, U / DINAJPUR, 733134</div>
                    <div class="title">ANNUAL RESULT - 2025</div>
                </div>
                <table class="info-tbl">
                    <tr>
                        <td class="lbl-name">NAME</td>
                        <td style="width:40%"><span class="val green">{{ s.name }}</span></td>
                        <td class="lbl-class">CLASS</td>
                        <td style="width:10%"><span class="val">{{ s.class_name }}</span></td>
                        <td class="lbl-roll">ROLL</td>
                        <td style="width:10%"><span class="val">{{ s.roll }}</span></td>
                        <td class="lbl-sec">SEC</td>
                        <td style="width:10%"><span class="val">{{ s.section }}</span></td>
                    </tr>
                </table>
                <table>
                    <thead>
                        <tr class="th-main">
                            <th rowspan="3" style="width: 15%;">SUBJECT</th>
                            <th colspan="3" style="background:#0056b3;">1ST UNIT</th>
                            <th colspan="3" style="background:#1e7e34;">2ND UNIT</th>
                            <th colspan="4" style="background:#bd2130;">FINAL EXAM</th>
                            <th rowspan="3" style="background:#d39e00;">TOTAL<br>(200)</th>
                            <th rowspan="3" style="background:#333;">GR</th>
                        </tr>
                        <tr>
                            <th class="th-u1">OR</th><th class="th-u1">WR</th><th class="th-u1">TOT</th>
                            <th class="th-u2">OR</th><th class="th-u2">WR</th><th class="th-u2">TOT</th>
                            <th class="th-final">OR</th><th class="th-final">WR</th><th class="th-final">CT</th><th class="th-final">TOT</th>
                        </tr>
                        <tr>
                            <th class="th-u1" style="font-size:8pt">10</th><th class="th-u1" style="font-size:8pt">40</th><th class="th-u1 sub-tot">50</th>
                            <th class="th-u2" style="font-size:8pt">10</th><th class="th-u2" style="font-size:8pt">40</th><th class="th-u2 sub-tot">50</th>
                            <th class="th-final" style="font-size:8pt">20</th><th class="th-final" style="font-size:8pt">70</th><th class="th-final" style="font-size:8pt">10</th><th class="th-final sub-tot">100</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for sub in s.subjects %}
                        <tr>
                            <td style="text-align:left; font-weight:bold; padding-left:5px;">{{ sub.name }}</td>
                            <td class="bg-unit1">{{ sub.u1_o }}</td><td class="bg-unit1">{{ sub.u1_w }}</td><td class="bg-unit1 sub-tot">{{ sub.u1_tot }}</td>
                            <td class="bg-unit2">{{ sub.u2_o }}</td><td class="bg-unit2">{{ sub.u2_w }}</td><td class="bg-unit2 sub-tot">{{ sub.u2_tot }}</td>
                            <td class="bg-final">{{ sub.f_o }}</td><td class="bg-final">{{ sub.f_w }}</td><td class="bg-final">{{ sub.f_ct }}</td><td class="bg-final sub-tot">{{ sub.f_tot }}</td>
                            <td class="bg-total">{{ sub.grand }}</td><td class="bg-grade">{{ sub.grade }}</td>
                        </tr>
                        {% endfor %}
                        <tr style="border-top: 2px solid black;">
                            <td style="text-align:left; font-weight:bold; padding-left:5px;">ART</td>
                            <td colspan="3" class="bg-unit1">{{ s.art_u1 }}</td>
                            <td colspan="3" class="bg-unit2">{{ s.art_u2 }}</td>
                            <td colspan="4" class="bg-final">{{ s.art_f }}</td>
                            <td class="bg-total">{{ s.art_grand }}</td>
                            <td class="bg-grade">{{ s.art_grade }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div style="flex-grow: 1; display: flex; flex-direction: column;">
                <table class="footer-table">
                    <tr>
                        <td class="col-left">
                            <table class="sub-table">
                                <tr><th colspan="3" class="sub-header">ADDITIONAL SUBJECTS</th></tr>
                                <tr style="background:#eee"><th style="text-align:left">SUBJECT</th><th>F.M</th><th>OBT</th></tr>
                                <tr><td style="text-align:left">PHYSICAL EDUCATION</td><td>20</td><td>{{ s.add.ped }}</td></tr>
                                <tr><td style="text-align:left">WORK EDUCATION</td><td>30</td><td>{{ s.add.wed }}</td></tr>
                                <tr><td style="text-align:left">HAND WRITING</td><td>20</td><td>{{ s.add.hw }}</td></tr>
                                <tr><td style="text-align:left">BEHAVIOUR</td><td>20</td><td>{{ s.add.behav }}</td></tr>
                                <tr><td style="text-align:left">ATTENDANCE</td><td>10</td><td>{{ s.add.attend }}</td></tr>
                                <tr class="bg-total"><td style="text-align:left">TOTAL</td><td>100</td><td>{{ s.add_tot }}</td></tr>
                            </table>
                            <table class="sub-table summary-box">
                                <tr><th colspan="2" class="sub-header" style="background-color:#000;">RESULT ABSTRACT</th></tr>
                                <tr><td style="text-align:left; font-weight:bold;">GRAND TOTAL ({{ s.max_marks }})</td><td>{{ s.total_obtained }}</td></tr>
                                <tr><td style="text-align:left; font-weight:bold;">PERCENTAGE</td><td>{{ s.percentage }}%</td></tr>
                                <tr><td style="text-align:left; font-weight:bold;">CLASS RANK</td><td>{{ s.rank }}</td></tr>
                                <tr style="background:#ffffcc"><td style="text-align:left; font-weight:bold;">OVERALL GRADE</td><td style="color:red; font-size:12pt; font-weight:900;">{{ s.overall_grade }}</td></tr>
                            </table>
                        </td>
                        <td class="col-right">
                            <table class="sub-table">
                                <tr class="sub-header"><th>MARKS RANGE</th><th>GRADE</th></tr>
                                <tr><td>180 - 200</td><td>AA</td></tr>
                                <tr><td>160 - 179</td><td>A+</td></tr>
                                <tr><td>120 - 159</td><td>A</td></tr>
                                <tr><td>90 - 119</td><td>B+</td></tr>
                                <tr><td>70 - 89</td><td>B</td></tr>
                                <tr><td>50 - 69</td><td>C</td></tr>
                                <tr><td>BELOW 50</td><td>D</td></tr>
                            </table>
                            <div class="stamp-container">
                                <img src="https://i.ibb.co/LhYbFJR0/20250604-163002-removebg-preview.png" style="width:110px; opacity:0.9;">
                                <div class="passed">PASSED</div>
                            </div>
                        </td>
                    </tr>
                </table>
                <div class="sig-row">
                    <div class="sig-box">Signature of Guardian</div>
                    <div class="sig-box">Signature of Class Teacher</div>
                    <div class="sig-box"><img src="https://i.ibb.co/ZpFHtpFx/20250604-163654-removebg-preview.png" class="tic-img">Signature of T.I.C</div>
                </div>
            </div>
        </div>
    </div>
    {% endfor %}
</body>
</html>
"""

# 2. HELPER FUNCTIONS
def get_val(val):
    """Safely return float value for calculation, treating 'AB' or empty as 0."""
    if pd.isna(val) or str(val).strip() == '':
        return 0.0
    if str(val).upper().strip() == 'AB':
        return 0.0
    try:
        return float(val)
    except:
        return 0.0

def calculate_grade(marks):
    try:
        # Check if marks is a valid number for grading
        if isinstance(marks, str):
             # If it's still a string here, it might be 'AB' or '-'
             return 'D' 
        m = float(marks)
        if 180 <= m <= 200: return 'AA'
        if 160 <= m <= 179: return 'A+'
        if 120 <= m <= 159: return 'A'
        if 90 <= m <= 119: return 'B+'
        if 70 <= m <= 89: return 'B'
        if 50 <= m <= 69: return 'C'
        return 'D'
    except:
        return '-'

def calculate_overall_grade(percentage):
    score = (percentage / 100) * 200
    return calculate_grade(score)

def fix_header_name(header):
    h = str(header).strip()
    h = re.sub(r'_(ORAL|Or|OR)$', '_Oral', h, flags=re.IGNORECASE)
    h = re.sub(r'_WR$', '_Wr', h, flags=re.IGNORECASE)
    h = re.sub(r'_ct$', '_CT', h, flags=re.IGNORECASE)
    return h

# 3. MAIN PROCESSING
def process_data(input_file):
    if not os.path.exists(input_file):
        print(f"Error: The file '{input_file}' was not found.")
        return

    try:
        df = pd.read_excel(input_file)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # Clean Headers
    df.columns = [fix_header_name(col) for col in df.columns]
    
    # ---------------------------------------------------------
    # DYNAMIC SUBJECT DETECTION
    # ---------------------------------------------------------
    # We define all possible subjects first
    all_main_subjects = [
        {'name': 'BENGALI', 'prefix': 'Beng'},
        {'name': 'ENGLISH', 'prefix': 'Eng'},
        {'name': 'MATHEMATICS', 'prefix': 'Math'},
        {'name': 'G.K.', 'prefix': 'GK'},
        {'name': 'E.V.S', 'prefix': 'EVNS'}, 
        {'name': 'HINDI', 'prefix': 'HIN'},
        {'name': 'ARABIC', 'prefix': 'ARB'}
    ]
    
    active_main_subjects = []
    
    # 1. Check Main Subjects
    # A subject is "active" if the sum of all its columns across all students > 0
    for sub in all_main_subjects:
        prefix = sub['prefix']
        # List of columns for this subject
        cols = [
            f'{prefix}_1_Oral', f'{prefix}_1_Wr',
            f'{prefix}_2_Oral', f'{prefix}_2_Wr',
            f'{prefix}_F_Oral', f'{prefix}_F_Wr', f'{prefix}_F_CT'
        ]
        
        subject_total_score = 0
        for col in cols:
            if col in df.columns:
                # Sum the column, treating non-numeric as 0
                col_sum = df[col].apply(get_val).sum()
                subject_total_score += col_sum
        
        if subject_total_score > 0:
            active_main_subjects.append(sub)
        else:
            print(f"Skipping Subject: {sub['name']} (Total score is 0 for all students)")

    # 2. Check Art
    art_cols = ['Art_1', 'Art_2', 'Art_Wr']
    art_total_score = 0
    for col in art_cols:
        if col in df.columns:
            art_total_score += df[col].apply(get_val).sum()
    
    is_art_active = art_total_score > 0
    if not is_art_active:
        print("Skipping Subject: ART (Total score is 0)")

    # 3. Check Additional
    add_cols = ['P.ED', 'W.ED', 'H.W', 'Behav', 'Attend']
    add_total_score = 0
    for col in add_cols:
        if col in df.columns:
            add_total_score += df[col].apply(get_val).sum()
            
    is_add_active = add_total_score > 0
    if not is_add_active:
        print("Skipping: Additional Subjects (Total score is 0)")

    # ---------------------------------------------------------
    # MAX MARKS CALCULATION
    # ---------------------------------------------------------
    # Main subjects = 200 each
    # Art = 100 (Assumed standard for report total)
    # Additional = 100
    calculated_max_marks = (len(active_main_subjects) * 200)
    if is_art_active:
        calculated_max_marks += 200 # Assuming Art is also 200 based on previous context, or 100? 
        # Note: In previous scripts we added Art marks to total. If Art has 100 max marks, change this to 100.
        # Based on "Total (200)" header in your HTML, let's assume Art is on 200 scale? 
        # Actually, looking at the HTML, Art row format mimics others. I will use 200 to be safe.
        # If Art is actually out of 100, change this line to += 100.
        pass 

    if is_add_active:
        calculated_max_marks += 100

    # However, strictly speaking, typically Art is 100 and Main are 200. 
    # Let's check your specific request: "beng(200)... art(200)". Okay, Art is 200.
    # So:
    final_max_marks = (len(active_main_subjects) * 200) + (200 if is_art_active else 0) + (100 if is_add_active else 0)
    
    print(f"Active Main Subjects: {len(active_main_subjects)}")
    print(f"Art Active: {is_art_active}")
    print(f"Additional Active: {is_add_active}")
    print(f"Calculated Grand Total Max Marks: {final_max_marks}")

    # ---------------------------------------------------------
    # PROCESS ROWS
    # ---------------------------------------------------------
    # Fill NaN with 0 for safety now
    df.fillna(0, inplace=True)

    students_list = []

    for index, row in df.iterrows():
        s = {}
        s['name'] = row.get('Name', '')
        s['class_name'] = row.get('Class', '')
        s['roll'] = row.get('Roll', '')
        s['section'] = row.get('Section', '')
        
        subjects_data = []
        grand_total_obtained = 0
        
        # Only iterate over ACTIVE subjects
        for sub in active_main_subjects:
            prefix = sub['prefix']
            subj_entry = {'name': sub['name']}
            
            # Fetch raw (for display)
            raw_u1_o = row.get(f'{prefix}_1_Oral', 0)
            raw_u1_w = row.get(f'{prefix}_1_Wr', 0)
            raw_u2_o = row.get(f'{prefix}_2_Oral', 0)
            raw_u2_w = row.get(f'{prefix}_2_Wr', 0)
            raw_f_o = row.get(f'{prefix}_F_Oral', 0)
            raw_f_w = row.get(f'{prefix}_F_Wr', 0)
            raw_f_ct = row.get(f'{prefix}_F_CT', 0)
            
            subj_entry['u1_o'] = raw_u1_o
            subj_entry['u1_w'] = raw_u1_w
            subj_entry['u2_o'] = raw_u2_o
            subj_entry['u2_w'] = raw_u2_w
            subj_entry['f_o'] = raw_f_o
            subj_entry['f_w'] = raw_f_w
            subj_entry['f_ct'] = raw_f_ct
            
            # Calc Values
            num_u1_tot = get_val(raw_u1_o) + get_val(raw_u1_w)
            num_u2_tot = get_val(raw_u2_o) + get_val(raw_u2_w)
            num_f_tot = get_val(raw_f_o) + get_val(raw_f_w) + get_val(raw_f_ct)
            num_grand = num_u1_tot + num_u2_tot + num_f_tot
            
            subj_entry['u1_tot'] = num_u1_tot
            subj_entry['u2_tot'] = num_u2_tot
            subj_entry['f_tot'] = num_f_tot
            subj_entry['grand'] = num_grand
            subj_entry['grade'] = calculate_grade(num_grand)
            
            grand_total_obtained += num_grand
            subjects_data.append(subj_entry)
            
        s['subjects'] = subjects_data
        
        # --- Art ---
        # Note: We display Art row even if inactive? Usually yes, empty. 
        # But if we removed it from Max Marks, we shouldn't add to Total Obtained.
        raw_art_u1 = row.get('Art_1', 0)
        raw_art_u2 = row.get('Art_2', 0)
        raw_art_f = row.get('Art_Wr', 0)
        
        s['art_u1'] = raw_art_u1
        s['art_u2'] = raw_art_u2
        s['art_f'] = raw_art_f
        
        art_tot = get_val(raw_art_u1) + get_val(raw_art_u2) + get_val(raw_art_f)
        s['art_grand'] = art_tot
        s['art_grade'] = calculate_grade(art_tot)
        
        if is_art_active:
            grand_total_obtained += art_tot
        
        # --- Additional ---
        raw_ped = row.get('P.ED', 0)
        raw_wed = row.get('W.ED', 0)
        raw_hw = row.get('H.W', 0)
        raw_behav = row.get('Behav', 0)
        raw_attend = row.get('Attend', 0)
        
        s['add'] = {
            'ped': raw_ped, 'wed': raw_wed, 'hw': raw_hw, 
            'behav': raw_behav, 'attend': raw_attend
        }
        add_tot = get_val(raw_ped) + get_val(raw_wed) + get_val(raw_hw) + get_val(raw_behav) + get_val(raw_attend)
        s['add_tot'] = add_tot
        
        if is_add_active:
            grand_total_obtained += add_tot
        
        # --- Final ---
        s['total_obtained'] = grand_total_obtained
        s['max_marks'] = final_max_marks
        
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
    process_data("student.xlsx")
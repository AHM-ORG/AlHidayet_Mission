import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations()
            super().showPage()
        super().save()

    def draw_page_decorations(self):
        # Outer Double Border
        self.saveState()
        self.setLineWidth(2.5)
        self.setStrokeColor(colors.black)
        self.rect(12, 12, 571, 818)
        self.setLineWidth(1)
        self.rect(15, 15, 565, 812)
        
        # Soft Yellow Page Background
        self.setFillColor(colors.HexColor('#FFFFF0'))
        self.rect(16, 16, 563, 810, fill=1, stroke=0)
        self.restoreState()


def generate_marksheet_pdf(student_info, marks_data, exam_type='annual', additional_marks=None, result_summary=None):
    """
    Generates a 100% pixel-perfect, single-page vector A4 Marksheet PDF.
    """
    buffer = io.BytesIO()
    
    # Page setup: A4 (595.27 x 841.89 pt)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18
    )

    styles = getSampleStyleSheet()
    
    # Custom Paragraph Styles
    style_title = ParagraphStyle(
        'SchoolTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=20,
        textColor=colors.HexColor('#d60000'),
        alignment=1
    )
    
    style_addr = ParagraphStyle(
        'SchoolAddr',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#444444'),
        alignment=1
    )

    style_badge = ParagraphStyle(
        'TitleBadge',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.white,
        alignment=1
    )

    style_header_lbl = ParagraphStyle(
        'HdrLbl',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )

    style_val_green = ParagraphStyle(
        'ValGreen',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#006400'),
        alignment=0
    )

    style_val_dark = ParagraphStyle(
        'ValDark',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.black,
        alignment=0
    )

    style_tbl_hdr = ParagraphStyle(
        'TblHdr',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=1
    )

    style_tbl_cell = ParagraphStyle(
        'TblCell',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=colors.black,
        alignment=1
    )

    style_tbl_cell_left = ParagraphStyle(
        'TblCellLeft',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.black,
        alignment=0
    )

    elements = []

    # 1. Header Section
    logo_path = 'static/images/logo.png'
    if not os.path.exists(logo_path):
        logo_path = None

    header_table_data = [
        [
            Image(logo_path, width=42, height=42) if logo_path else '',
            [
                Paragraph("BHOGRAM AL-HIDAYET MISSION", style_title),
                Spacer(1, 1),
                Paragraph("BHOGRAM, P.O &ndash; BHOGRAM, P.S &ndash; HEMTABAD, U / DINAJPUR, 733134", style_addr),
                Spacer(1, 2),
                Table([[Paragraph(f"{exam_type.upper()} RESULT - 2025", style_badge)]],
                      colWidths=[180],
                      style=[
                          ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#d60000')),
                          ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                          ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                          ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                          ('TOPPADDING', (0, 0), (-1, -1), 2),
                      ])
            ],
            Image(logo_path, width=42, height=42) if logo_path else ''
        ]
    ]

    hdr_table = Table(header_table_data, colWidths=[50, 459, 50])
    hdr_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(hdr_table)
    elements.append(Spacer(1, 4))

    # 2. Student Info Table
    info_data = [
        [
            Paragraph("NAME", style_header_lbl),
            Paragraph(student_info.get('full_name') or student_info.get('name') or 'MAHIR RAHAMAN', style_val_green),
            Paragraph("CLASS", style_header_lbl),
            Paragraph(str(student_info.get('class') or 'U/N'), style_val_dark),
            Paragraph("ROLL", style_header_lbl),
            Paragraph(str(student_info.get('roll_number') or '1'), style_val_dark),
            Paragraph("SEC", style_header_lbl),
            Paragraph(str(student_info.get('section') or 'A'), style_val_dark),
        ]
    ]
    info_tbl = Table(info_data, colWidths=[45, 214, 45, 60, 45, 50, 40, 60])
    info_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#1a237e')),
        ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#1a237e')),
        ('BACKGROUND', (4, 0), (4, 0), colors.HexColor('#1a237e')),
        ('BACKGROUND', (6, 0), (6, 0), colors.HexColor('#1a237e')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 4))

    # 3. Main Academic Table (Annual Composite / Term)
    main_headers = [
        [
            Paragraph("SUBJECT", style_tbl_hdr),
            Paragraph("1ST UNIT", style_tbl_hdr), "", "",
            Paragraph("2ND UNIT", style_tbl_hdr), "", "",
            Paragraph("FINAL EXAM", style_tbl_hdr), "", "", "",
            Paragraph("TOTAL<br/>(200)", style_tbl_hdr),
            Paragraph("GR", style_tbl_hdr)
        ],
        [
            "",
            Paragraph("OR", style_tbl_hdr), Paragraph("WR", style_tbl_hdr), Paragraph("TOT", style_tbl_hdr),
            Paragraph("OR", style_tbl_hdr), Paragraph("WR", style_tbl_hdr), Paragraph("TOT", style_tbl_hdr),
            Paragraph("OR", style_tbl_hdr), Paragraph("WR", style_tbl_hdr), Paragraph("CT", style_tbl_hdr), Paragraph("TOT", style_tbl_hdr),
            "", ""
        ],
        [
            "",
            Paragraph("10", style_tbl_hdr), Paragraph("40", style_tbl_hdr), Paragraph("50", style_tbl_hdr),
            Paragraph("10", style_tbl_hdr), Paragraph("40", style_tbl_hdr), Paragraph("50", style_tbl_hdr),
            Paragraph("20", style_tbl_hdr), Paragraph("70", style_tbl_hdr), Paragraph("10", style_tbl_hdr), Paragraph("100", style_tbl_hdr),
            "", ""
        ]
    ]

    main_rows = main_headers.copy()

    # Populate subject rows
    subjects_list = marks_data.get('subjects', []) if isinstance(marks_data, dict) else []
    if not subjects_list:
        subjects_list = [
            {'name': 'ARABIC', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'BENGALI', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'E.V.S', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'ENGLISH', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'G.K.', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'HINDI', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'MATHEMATICS', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'SCIENCE', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'ART', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
            {'name': 'TOTAL', 'u1O': '-', 'u1W': '-', 'u1Tot': '-', 'u2O': '-', 'u2W': '-', 'u2Tot': '-', 'fO': '-', 'fW': '-', 'fCt': '-', 'fTot': '-', 'grand': '-', 'grade': '-'},
        ]

    for sub in subjects_list:
        main_rows.append([
            Paragraph(sub.get('name', ''), style_tbl_cell_left),
            Paragraph(str(sub.get('u1O', '-')), style_tbl_cell),
            Paragraph(str(sub.get('u1W', '-')), style_tbl_cell),
            Paragraph(str(sub.get('u1Tot', '-')), style_tbl_cell),
            Paragraph(str(sub.get('u2O', '-')), style_tbl_cell),
            Paragraph(str(sub.get('u2W', '-')), style_tbl_cell),
            Paragraph(str(sub.get('u2Tot', '-')), style_tbl_cell),
            Paragraph(str(sub.get('fO', '-')), style_tbl_cell),
            Paragraph(str(sub.get('fW', '-')), style_tbl_cell),
            Paragraph(str(sub.get('fCt', '-')), style_tbl_cell),
            Paragraph(str(sub.get('fTot', '-')), style_tbl_cell),
            Paragraph(str(sub.get('grand', '-')), style_tbl_cell),
            Paragraph(str(sub.get('grade', '-')), style_tbl_cell),
        ])

    col_w = [125, 33, 33, 37, 33, 33, 37, 33, 33, 33, 40, 56, 33]
    main_tbl = Table(main_rows, colWidths=col_w)
    
    t_style = [
        ('GRID', (0, 0), (-1, -1), 0.8, colors.HexColor('#444444')),
        ('SPAN', (0, 0), (0, 2)),    # Subject
        ('SPAN', (1, 0), (3, 0)),    # 1st Unit
        ('SPAN', (4, 0), (6, 0)),    # 2nd Unit
        ('SPAN', (7, 0), (10, 0)),   # Final Exam
        ('SPAN', (11, 0), (11, 2)),  # Total
        ('SPAN', (12, 0), (12, 2)),  # Grade
        ('BACKGROUND', (0, 0), (0, 2), colors.HexColor('#333333')),
        ('BACKGROUND', (1, 0), (3, 0), colors.HexColor('#0056b3')),
        ('BACKGROUND', (4, 0), (6, 0), colors.HexColor('#1e7e34')),
        ('BACKGROUND', (7, 0), (10, 0), colors.HexColor('#bd2130')),
        ('BACKGROUND', (11, 0), (11, 2), colors.HexColor('#d39e00')),
        ('BACKGROUND', (12, 0), (12, 2), colors.HexColor('#333333')),
        ('BACKGROUND', (1, 1), (3, 2), colors.HexColor('#cce5ff')),
        ('BACKGROUND', (4, 1), (6, 2), colors.HexColor('#d4edda')),
        ('BACKGROUND', (7, 1), (10, 2), colors.HexColor('#f8d7da')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]

    main_tbl.setStyle(TableStyle(t_style))
    elements.append(main_tbl)
    elements.append(Spacer(1, 4))

    # 4. Footer Section (Left Column: Additional + Abstract, Right Column: Range + Stamp)
    # Left Column: Additional Subjects Table
    add_data = [
        [Paragraph("ADDITIONAL SUBJECTS", style_tbl_hdr), "", ""],
        [Paragraph("SUBJECT", style_tbl_cell_left), Paragraph("F.M", style_tbl_hdr), Paragraph("OBT", style_tbl_hdr)],
        [Paragraph("PHYSICAL EDUCATION", style_tbl_cell_left), Paragraph("100", style_tbl_cell), Paragraph("-", style_tbl_cell)],
        [Paragraph("WORK EDUCATION", style_tbl_cell_left), Paragraph("100", style_tbl_cell), Paragraph("-", style_tbl_cell)],
        [Paragraph("HAND WRITING", style_tbl_cell_left), Paragraph("100", style_tbl_cell), Paragraph("-", style_tbl_cell)],
        [Paragraph("BEHAVIOUR", style_tbl_cell_left), Paragraph("100", style_tbl_cell), Paragraph("-", style_tbl_cell)],
        [Paragraph("ATTENDANCE", style_tbl_cell_left), Paragraph("100", style_tbl_cell), Paragraph("-", style_tbl_cell)],
        [Paragraph("TOTAL", style_tbl_cell_left), Paragraph("500", style_tbl_cell), Paragraph("-", style_tbl_cell)],
    ]
    add_tbl = Table(add_data, colWidths=[140, 65, 65])
    add_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.8, colors.black),
        ('SPAN', (0, 0), (2, 0)),
        ('BACKGROUND', (0, 0), (2, 0), colors.HexColor('#333333')),
        ('BACKGROUND', (0, 1), (2, 1), colors.HexColor('#eee')),
        ('BACKGROUND', (0, 7), (2, 7), colors.HexColor('#fff9db')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))

    # Left Column: Result Abstract Table
    res_data = [
        [Paragraph("RESULT ABSTRACT", style_tbl_hdr), ""],
        [Paragraph("GRAND TOTAL (0)", style_tbl_cell_left), Paragraph("0", style_tbl_cell)],
        [Paragraph("PERCENTAGE", style_tbl_cell_left), Paragraph("0.0%", style_tbl_cell)],
        [Paragraph("CLASS RANK", style_tbl_cell_left), Paragraph("-", style_tbl_cell)],
        [Paragraph("OVERALL GRADE", style_tbl_cell_left), Paragraph("D", style_tbl_cell)],
    ]
    res_tbl = Table(res_data, colWidths=[170, 100])
    res_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.8, colors.black),
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#333333')),
        ('BACKGROUND', (0, 4), (1, 4), colors.HexColor('#ffffcc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    left_col_content = [add_tbl, Spacer(1, 4), res_tbl]

    # Right Column: Marks Range Table
    range_data = [
        [Paragraph("MARKS RANGE", style_tbl_hdr), ""],
        [Paragraph("RANGE", style_tbl_cell), Paragraph("GRADE", style_tbl_cell)],
        [Paragraph("180 - 200", style_tbl_cell), Paragraph("AA", style_tbl_cell)],
        [Paragraph("160 - 179", style_tbl_cell), Paragraph("A+", style_tbl_cell)],
        [Paragraph("120 - 159", style_tbl_cell), Paragraph("A", style_tbl_cell)],
        [Paragraph("90 - 119", style_tbl_cell), Paragraph("B+", style_tbl_cell)],
        [Paragraph("70 - 89", style_tbl_cell), Paragraph("B", style_tbl_cell)],
        [Paragraph("50 - 69", style_tbl_cell), Paragraph("C", style_tbl_cell)],
        [Paragraph("BELOW 50", style_tbl_cell), Paragraph("D", style_tbl_cell)],
    ]
    range_tbl = Table(range_data, colWidths=[150, 120])
    range_tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.8, colors.black),
        ('SPAN', (0, 0), (1, 0)),
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#333333')),
        ('BACKGROUND', (0, 1), (1, 1), colors.HexColor('#eee')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))

    # Stamp Table
    stamp_badge = Table([[Paragraph("PASSED", ParagraphStyle('PassBadge', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#2e7d32'), alignment=1))]],
                        colWidths=[80],
                        style=[
                            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f5e9')),
                            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#2e7d32')),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('TOPPADDING', (0, 0), (-1, -1), 3),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                        ])
    
    right_col_content = [range_tbl, Spacer(1, 8), stamp_badge]

    # Combine Left and Right into 2-Column Outer Footer Table
    footer_outer_data = [[left_col_content, right_col_content]]
    footer_outer_tbl = Table(footer_outer_data, colWidths=[275, 284])
    footer_outer_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(footer_outer_tbl)
    elements.append(Spacer(1, 12))

    # 5. Signatures Table
    sig_data = [
        [
            Paragraph("Signature of Guardian", ParagraphStyle('SigLbl', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
            Paragraph("Signature of Class Teacher", ParagraphStyle('SigLbl', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
            Paragraph("Signature of T.I.C", ParagraphStyle('SigLbl', fontName='Helvetica-Bold', fontSize=8.5, alignment=1))
        ]
    ]
    sig_tbl = Table(sig_data, colWidths=[180, 180, 180])
    sig_tbl.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 1.5, colors.black),
        ('LINEABOVE', (1, 0), (1, 0), 1.5, colors.black),
        ('LINEABOVE', (2, 0), (2, 0), 1.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(sig_tbl)

    # Build PDF with NumberedCanvas double border
    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

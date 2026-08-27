from datetime import datetime
from evaluation import run_evaluation
from database import get_session_by_id
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import textwrap

def generate_report(name, roll, experiment, responses):
    total = run_evaluation()  # pass responses here
    max_marks = len(responses) * 2

    report = {
        "timestamp": datetime.now().isoformat(),
        "name": name,
        "roll": roll,
        "experiment": experiment,
        "total": total,
        "max_marks": max_marks
    }

    return report


def generate_pdf_report(session_id):
    """Generate a PDF report for a viva session."""
    data = get_session_by_id(session_id)
    if not data:
        return None
        
    session = data["session"]
    answers = data["answers"]
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1  # Center
    
    normal_style = styles['Normal']
    normal_style.fontSize = 10
    
    bold_style = ParagraphStyle(
        'BoldStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10
    )
    
    elements = []
    
    # Header
    elements.append(Paragraph("<b>AI VIVA AGENT - EXAMINATION REPORT</b>", title_style))
    elements.append(Spacer(1, 20))
    
    # Student Info Table
    info_data = [
        ["Student Name:", session["student_name"], "Subject:", session["subject"]],
        ["Roll No:", session["roll_no"], "Date:", session["timestamp"][:10]],
        ["Score:", f"{session['total_score']} / {session['max_marks']}", "Grade:", session["grade"]]
    ]
    
    info_table = Table(info_data, colWidths=[80, 180, 60, 180])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 30))
    
    # Detailed Q&A
    elements.append(Paragraph("<b>DETAILED EVALUATION</b>", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    for ans in answers:
        q_num = ans["question_number"]
        
        # Format text to wrap properly in PDF
        q_text = Paragraph(f"<b>Q{q_num}: {ans['question']}</b>", normal_style)
        
        # User answer
        u_ans_raw = ans['student_answer']
        if not u_ans_raw:
            u_ans_raw = "(No answer provided)"
        u_ans = Paragraph(f"<i>Student:</i> {u_ans_raw}", normal_style)
        
        # AI Verdict
        verdict = ans['verdict'].upper()
        verdict_color = colors.green if verdict == "CORRECT" else (colors.orange if verdict == "PARTIALLY CORRECT" else colors.red)
        v_text = f"<font color='{verdict_color}'><b>[{verdict}]</b></font> (Score: {ans['score']}/2)"
        v_para = Paragraph(v_text, normal_style)
        
        # Correct answer
        c_ans = Paragraph(f"<i>Reference:</i> {ans['correct_answer']}", normal_style)
        
        elements.append(q_text)
        elements.append(Spacer(1, 4))
        elements.append(u_ans)
        elements.append(Spacer(1, 4))
        elements.append(v_para)
        elements.append(Spacer(1, 4))
        elements.append(c_ans)
        elements.append(Spacer(1, 15))
        
    # Build PDF
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

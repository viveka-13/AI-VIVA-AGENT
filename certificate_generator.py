"""Create and store completion certificates for passed Viva Agent sessions."""
import io
import os
import uuid
from datetime import datetime
from html import escape

import database
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


CERTIFICATES_DIR = os.path.join(os.path.dirname(__file__), "faculty_data", "certificates")


def _completion_date(timestamp):
    try:
        return datetime.fromisoformat(timestamp).strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return str(timestamp)


def _draw_certificate_frame(canvas, document):
    page_width, page_height = landscape(A4)
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1f3552"))
    canvas.setStrokeColor(colors.HexColor("#1f3552"))
    canvas.setLineWidth(2)
    canvas.rect(24, 24, page_width - 48, page_height - 48, fill=0, stroke=1)
    canvas.setStrokeColor(colors.HexColor("#b08d57"))
    canvas.setLineWidth(0.8)
    canvas.rect(32, 32, page_width - 64, page_height - 64, fill=0, stroke=1)

    seal_x = page_width - 0.9 * inch
    seal_y = 0.85 * inch
    canvas.setFillColor(colors.HexColor("#b08d57"))
    canvas.circle(seal_x, seal_y, 0.36 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Times-Bold", 9)
    canvas.drawCentredString(seal_x, seal_y - 3, "VIVA")
    canvas.restoreState()


def generate_certificate_pdf(session, certificate_id):
    """Build a one-page landscape PDF using the finalized session record."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.7 * inch,
        bottomMargin=1.2 * inch,
    )
    base_styles = getSampleStyleSheet()
    kicker_style = ParagraphStyle(
        "CertificateKicker",
        parent=base_styles["Normal"],
        fontName="Times-Bold",
        fontSize=12,
        leading=16,
        alignment=1,
        textColor=colors.HexColor("#8a6d3b"),
    )
    title_style = ParagraphStyle(
        "CertificateTitle",
        parent=base_styles["Title"],
        fontName="Times-Bold",
        fontSize=30,
        leading=36,
        alignment=1,
        textColor=colors.HexColor("#1f3552"),
    )
    body_style = ParagraphStyle(
        "CertificateBody",
        parent=base_styles["Normal"],
        fontName="Times-Roman",
        fontSize=15,
        leading=22,
        alignment=1,
        textColor=colors.HexColor("#333333"),
    )
    student_style = ParagraphStyle(
        "CertificateStudent",
        parent=body_style,
        fontName="Times-Bold",
        fontSize=25,
        leading=31,
        textColor=colors.HexColor("#1f3552"),
    )
    detail_style = ParagraphStyle(
        "CertificateDetails",
        parent=body_style,
        fontSize=12,
        leading=17,
    )

    student_name = escape(str(session["student_name"]))
    subject = escape(str(session["subject"]))
    completed = escape(_completion_date(session["timestamp"]))
    score = f'{session["total_score"]} / {session["max_marks"]}'
    grade = escape(str(session["grade"]))

    score_table = Table(
        [["FINAL SCORE", "GRADE"], [score, grade]],
        colWidths=[2.3 * inch, 1.5 * inch],
        rowHeights=[0.3 * inch, 0.42 * inch],
        hAlign="CENTER",
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3552")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 15),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#1f3552")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#b08d57")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b08d57")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story = [
        Spacer(1, 0.12 * inch),
        Paragraph("AI VIVA AGENT", kicker_style),
        Spacer(1, 0.12 * inch),
        Paragraph("Certificate of Completion", title_style),
        Spacer(1, 0.2 * inch),
        Paragraph("This certificate is proudly presented to", body_style),
        Spacer(1, 0.12 * inch),
        Paragraph(student_name, student_style),
        Spacer(1, 0.12 * inch),
        Paragraph(f"for successfully completing the <b>{subject}</b> viva assessment.", body_style),
        Spacer(1, 0.2 * inch),
        score_table,
        Spacer(1, 0.15 * inch),
        Paragraph(f"Completed on {completed}", detail_style),
        Spacer(1, 0.08 * inch),
        Paragraph(f"Certificate ID: <b>{escape(certificate_id)}</b>", detail_style),
        Paragraph(
            f"Verify at /certificate/verify/{escape(certificate_id)}",
            ParagraphStyle("CertificateVerify", parent=detail_style, fontSize=9),
        ),
    ]

    document.build(story, onFirstPage=_draw_certificate_frame)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


def ensure_certificate(session_id):
    """Ensure a certificate PDF exists for a finalized passing session."""
    session_data = database.get_session_by_id(session_id)
    if not session_data:
        return None

    session = session_data["session"]
    if session["status"] != "completed" or not session["passed"]:
        return None

    answers = session_data["answers"]
    if not answers or any(not answer["student_answer"].strip() for answer in answers):
        return None

    assigned_questions = database.get_assigned_questions(session_id)
    if assigned_questions:
        assigned_text = sorted(question["question"] for question in assigned_questions)
        evaluated_text = sorted(answer["question"] for answer in answers)
        if assigned_text != evaluated_text:
            return None

    record = database.get_certificate_for_session(session_id)
    if record and os.path.isfile(record["file_path"]):
        return record

    if not record:
        certificate_id = f"VIVA-{uuid.uuid4().hex[:16].upper()}"
        file_path = os.path.join(CERTIFICATES_DIR, f"{certificate_id}.pdf")
        record = database.create_certificate_record(
            session_id=session_id,
            certificate_id=certificate_id,
            file_path=file_path,
            generated_at=datetime.now().isoformat(),
        )
        if not record:
            return None

    os.makedirs(CERTIFICATES_DIR, exist_ok=True)
    temporary_path = f'{record["file_path"]}.{uuid.uuid4().hex}.tmp'
    try:
        pdf_data = generate_certificate_pdf(session, record["certificate_id"])
        with open(temporary_path, "wb") as certificate_file:
            certificate_file.write(pdf_data)
        os.replace(temporary_path, record["file_path"])
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

    return database.get_certificate_for_session(session_id)

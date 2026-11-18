"""
ReportLab PDF Generation Service
Cloud-Based PDF Generation System - Milestone 2

Handles professional PDF document composition:
- Multi-page document flows
- Two-pass NumberedCanvas for accurate "Page X of Y" page numbering
- Custom headers and footers with running rule lines
- Elegant typography, title blocks, metadata tables, and justified body content
"""
import io
import html
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
    KeepTogether
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render exact total page count
    ("Page X of Y"), along with running header and footer on every page.
    """
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
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        page_w, page_h = letter
        margin = 54  # 0.75 inch = 54 points

        # --- Running Header (on all pages) ---
        header_y = page_h - 36
        self.drawString(margin, header_y, "CloudPDF Studio • Cloud-Based PDF Generation System")
        self.drawRightString(page_w - margin, header_y, "AWS Cloud Architecture")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(margin, header_y - 6, page_w - margin, header_y - 6)

        # --- Running Footer (on all pages) ---
        footer_y = 36
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(margin, footer_y + 12, page_w - margin, footer_y + 12)

        self.drawString(margin, footer_y, "Generated via ReportLab Engine | Confidential & Academic Use")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_w - margin, footer_y, page_str)

        self.restoreState()


class PDFGeneratorService:
    """
    Core document compiler utilizing ReportLab Flowables.
    """
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._init_custom_styles()

    def _init_custom_styles(self):
        primary_color = colors.HexColor("#1e40af")   # Deep Blue
        text_dark = colors.HexColor("#0f172a")       # Slate 900
        text_muted = colors.HexColor("#475569")      # Slate 600

        # Title
        self.styles.add(ParagraphStyle(
            name="CloudTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=primary_color,
            spaceAfter=8
        ))

        # Description / Abstract block
        self.styles.add(ParagraphStyle(
            name="CloudDescription",
            parent=self.styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            leading=14,
            textColor=text_muted,
            spaceAfter=12
        ))

        # Section Heading
        self.styles.add(ParagraphStyle(
            name="CloudHeading",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=primary_color,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True
        ))

        # Body paragraph
        self.styles.add(ParagraphStyle(
            name="CloudBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=text_dark,
            alignment=4,  # Justified
            spaceAfter=8
        ))

        # Metadata cell text
        self.styles.add(ParagraphStyle(
            name="MetaLabel",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1e3a8a")
        ))
        self.styles.add(ParagraphStyle(
            name="MetaValue",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=text_dark
        ))

    def generate_pdf(self, title: str, author: str, description: str, content: str, doc_id: str) -> bytes:
        """
        Builds and returns the binary PDF bytes.
        """
        buffer = io.BytesIO()

        # Margins: 54pt (0.75 in) left/right, 54pt top/bottom
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54
        )

        story = []

        # Document Header Pill / Tag
        pill_style = ParagraphStyle(
            name="PillTag",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1d4ed8")
        )
        story.append(Paragraph("AWS CLOUD COMPUTING PROJECT • OFFICIAL DOCUMENTATION", pill_style))
        story.append(Spacer(1, 4))

        # Title
        safe_title = html.escape(title.strip())
        story.append(Paragraph(safe_title, self.styles["CloudTitle"]))

        # Optional Description
        if description and description.strip():
            safe_desc = html.escape(description.strip())
            story.append(Paragraph(safe_desc, self.styles["CloudDescription"]))

        # Metadata Summary Card (Author, Date, Document ID, Cloud Status)
        now_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")
        meta_data = [
            [
                Paragraph("<b>Document ID:</b>", self.styles["MetaLabel"]),
                Paragraph(html.escape(doc_id), self.styles["MetaValue"]),
                Paragraph("<b>Author / Creator:</b>", self.styles["MetaLabel"]),
                Paragraph(html.escape(author.strip()), self.styles["MetaValue"])
            ],
            [
                Paragraph("<b>Generated On:</b>", self.styles["MetaLabel"]),
                Paragraph(now_str, self.styles["MetaValue"]),
                Paragraph("<b>Cloud Storage:</b>", self.styles["MetaLabel"]),
                Paragraph("Amazon S3 (Planned M3)", self.styles["MetaValue"])
            ]
        ]

        meta_table = Table(meta_data, colWidths=[85, 160, 95, 164])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        ]))

        story.append(meta_table)
        story.append(Spacer(1, 14))

        # Accent Rule Divider
        story.append(HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#2563eb"),
            spaceBefore=4,
            spaceAfter=14
        ))

        # Section Heading
        story.append(Paragraph("Document Content", self.styles["CloudHeading"]))
        story.append(Spacer(1, 4))

        # Process Main Content paragraphs
        raw_paragraphs = content.split("\n")
        for raw_p in raw_paragraphs:
            cleaned = raw_p.strip()
            if not cleaned:
                # Blank line spacing
                story.append(Spacer(1, 6))
                continue

            # Sub-heading detection (e.g. lines starting with section markers or numbers)
            if cleaned.isupper() and len(cleaned) < 60:
                story.append(Spacer(1, 6))
                story.append(Paragraph(html.escape(cleaned), self.styles["CloudHeading"]))
                story.append(Spacer(1, 2))
            else:
                escaped_text = html.escape(cleaned)
                story.append(Paragraph(escaped_text, self.styles["CloudBody"]))

        # Build document with custom 2-pass NumberedCanvas
        doc.build(story, canvasmaker=NumberedCanvas)

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.logging import logger

FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"


def register_fonts() -> str:
    """
    Attempts to register a TrueType font for full Unicode support.
    Falls back gracefully to 'Helvetica' if TTF file is unavailable.
    """
    ttf_candidates = [
        FONTS_DIR / "DejaVuSans.ttf",
        FONTS_DIR / "NotoSans-Regular.ttf",
    ]

    for font_path in ttf_candidates:
        if font_path.exists():
            try:
                font_name = font_path.stem
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                return font_name
            except Exception as e:
                logger.warning(f"Failed to register TTF font {font_path}: {e}")

    return "Helvetica"


DEFAULT_FONT_NAME = register_fonts()


class CertificateGenerator:
    """Generates landscape A4 PDF certificates using ReportLab."""

    def __init__(self, font_name: str | None = None):
        self.font_name = font_name or DEFAULT_FONT_NAME

    def generate(
        self,
        recipient_name: str,
        event_name: str,
        issuer_name: str,
        issue_date: date | str,
        certificate_id: str,
    ) -> bytes:
        """
        Renders a certificate PDF to in-memory bytes.
        Automatically scales down recipient name font size for long names.
        """
        buffer = io.BytesIO()
        page_width, page_height = landscape(A4)

        c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
        c.setTitle(f"Certificate - {recipient_name}")

        # Decorative outer border
        c.setStrokeColor(colors.HexColor("#1E3A8A"))  # Dark Blue
        c.setLineWidth(3)
        c.rect(30, 30, page_width - 60, page_height - 60)

        c.setStrokeColor(colors.HexColor("#D97706"))  # Gold Accent
        c.setLineWidth(1)
        c.rect(36, 36, page_width - 72, page_height - 72)

        # Header Title
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.setFont(self.font_name, 28)
        c.drawCentredString(page_width / 2, page_height - 110, "CERTIFICATE OF COMPLETION")

        # Sub-header
        c.setFillColor(colors.HexColor("#4B5563"))  # Gray
        c.setFont(self.font_name, 14)
        c.drawCentredString(page_width / 2, page_height - 150, "This is proudly presented to")

        # Recipient Name with Auto-Shrink Font Size
        max_name_width = page_width - 140
        base_font_size = 32
        min_font_size = 12

        font_size = base_font_size
        text_width = pdfmetrics.stringWidth(recipient_name, self.font_name, font_size)

        if text_width > max_name_width and text_width > 0:
            scale_factor = max_name_width / text_width
            font_size = max(min_font_size, int(base_font_size * scale_factor))

        c.setFillColor(colors.HexColor("#111827"))  # Dark Charcoal
        c.setFont(self.font_name, font_size)
        c.drawCentredString(page_width / 2, page_height - 210, recipient_name)

        # Underline accent below recipient name
        c.setStrokeColor(colors.HexColor("#D97706"))
        c.setLineWidth(1.5)
        c.line(page_width / 2 - 150, page_height - 225, page_width / 2 + 150, page_height - 225)

        # Body Text
        c.setFillColor(colors.HexColor("#4B5563"))
        c.setFont(self.font_name, 14)
        c.drawCentredString(page_width / 2, page_height - 275, "for successfully participating in")

        # Event Name
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.setFont(self.font_name, 20)
        c.drawCentredString(page_width / 2, page_height - 315, event_name)

        # Date and Issuer Info
        formatted_date = (
            issue_date.strftime("%B %d, %Y") if isinstance(issue_date, date) else str(issue_date)
        )
        c.setFillColor(colors.HexColor("#374151"))
        c.setFont(self.font_name, 12)
        c.drawCentredString(
            page_width / 2, page_height - 380, f"Issued on {formatted_date} by {issuer_name}"
        )

        # Certificate Reference ID at Bottom
        c.setFillColor(colors.HexColor("#9CA3AF"))
        c.setFont(self.font_name, 9)
        c.drawCentredString(page_width / 2, 50, f"Certificate ID: {certificate_id}")

        c.showPage()
        c.save()

        buffer.seek(0)
        return buffer.getvalue()

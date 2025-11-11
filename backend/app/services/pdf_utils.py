from pathlib import Path
from typing import Optional, List

from pypdf import PdfReader

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import mm

from ..config import WINDOWS_MALGUN_TTF


def extract_text_from_pdf(pdf_path: Path) -> str:
	reader = PdfReader(str(pdf_path))
	text_parts: List[str] = []
	for page in reader.pages:
		page_text = page.extract_text() or ""
		text_parts.append(page_text)
	return "\n".join(text_parts)


def _ensure_korean_font() -> Optional[str]:
	"""
	Try to register a Korean font if available on Windows (Malgun Gothic).
	Returns the registered font name if successful.
	"""
	try:
		ttf_path = Path(WINDOWS_MALGUN_TTF)
		if ttf_path.exists():
			font_name = "MalgunGothic"
			if font_name not in pdfmetrics.getRegisteredFontNames():
				pdfmetrics.registerFont(TTFont(font_name, str(ttf_path)))
			return font_name
	except Exception:
		# Ignore font registration failure; will fallback to Helvetica
		pass
	return None


def create_pdf_from_text(text: str, output_path: Path):
	"""
	Create a simple PDF with translated text, using ReportLab with CJK wrapping.
	Tries to use Malgun Gothic if available for proper Korean rendering.
	"""
	output_path.parent.mkdir(parents=True, exist_ok=True)
	font_name = _ensure_korean_font() or "Helvetica"

	doc = SimpleDocTemplate(
		str(output_path),
		pagesize=A4,
		rightMargin=20 * mm,
		leftMargin=20 * mm,
		topMargin=20 * mm,
		bottomMargin=20 * mm,
	)

	styles = getSampleStyleSheet()
	body_style = ParagraphStyle(
		"Body",
		parent=styles["Normal"],
		fontName=font_name,
		fontSize=11,
		leading=16,
		wordWrap="CJK",  # better wrapping for Korean
	)

	flow = []
	for block in text.split("\n\n"):
		sanitized = block.replace("<", "&lt;").replace(">", "&gt;")
		flow.append(Paragraph(sanitized, style=body_style))
		flow.append(Spacer(1, 4 * mm))

	if not flow:
		flow.append(Paragraph(" ", style=body_style))

	doc.build(flow)



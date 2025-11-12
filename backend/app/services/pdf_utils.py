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

try:
	import fitz  # PyMuPDF
except Exception:
	fitz = None  # type: ignore

try:
	import pytesseract
	from pdf2image import convert_from_path
	from PIL import Image
except Exception:
	pytesseract = None  # type: ignore
	convert_from_path = None  # type: ignore
	Image = None  # type: ignore

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



def extract_layout_blocks(pdf_path: Path):
	"""
	Extract page sizes and text blocks (bbox + text + approx font size) using PyMuPDF.
	Returns a JSON-serializable dict:
	{
	  "pages": [
	    {
	      "width": float, "height": float,
	      "blocks": [
	        {"bbox": [x0,y0,x1,y1], "text": "....", "font_size": 12.3}
	      ]
	    },
	    ...
	  ]
	}
	"""
	if fitz is None:
		raise RuntimeError("PyMuPDF(fitz)가 설치되어 있지 않습니다. requirements.txt를 확인하세요.")

	doc = fitz.open(str(pdf_path))
	pages = []
	for page in doc:
		page_info = {"width": float(page.rect.width), "height": float(page.rect.height), "blocks": []}
		raw = page.get_text("rawdict")
		for b in raw.get("blocks", []):
			if "lines" not in b:
				continue
			x0, y0, x1, y1 = None, None, None, None
			spans_sizes = []
			text_parts = []
			for line in b.get("lines", []):
				line_text_parts = []
				for span in line.get("spans", []):
					t = span.get("text", "") or ""
					if t.strip():
						line_text_parts.append(t)
						spans_sizes.append(float(span.get("size", 0.0) or 0.0))
						sb = span.get("bbox", None)
						if sb and len(sb) == 4:
							sx0, sy0, sx1, sy1 = [float(v) for v in sb]
							x0 = sx0 if x0 is None else min(x0, sx0)
							y0 = sy0 if y0 is None else min(y0, sy0)
							x1 = sx1 if x1 is None else max(x1, sx1)
							y1 = sy1 if y1 is None else max(y1, sy1)
				if line_text_parts:
					# keep line breaks inside the block
					text_parts.append("".join(line_text_parts))
			block_text = "\n".join(text_parts).strip()
			if not block_text:
				continue
			if x0 is None or y0 is None or x1 is None or y1 is None:
				continue
			# representative font size: median of spans
			font_size = 0.0
			if spans_sizes:
				sorted_sizes = sorted(spans_sizes)
				mid = len(sorted_sizes) // 2
				if len(sorted_sizes) % 2 == 0:
					font_size = (sorted_sizes[mid - 1] + sorted_sizes[mid]) / 2.0
				else:
					font_size = sorted_sizes[mid]
			page_info["blocks"].append(
				{
					"bbox": [float(x0), float(y0), float(x1), float(y1)],
					"text": block_text,
					"font_size": float(font_size),
				}
			)
		pages.append(page_info)
	doc.close()
	return {"pages": pages}


def extract_layout_blocks_ocr(pdf_path: Path):
	"""
	Extract text blocks using OCR (Tesseract) for image-based PDFs.
	Returns same structure as extract_layout_blocks.
	Requires: pytesseract, pdf2image, Pillow, and tesseract binary installed.
	"""
	if pytesseract is None or convert_from_path is None:
		raise RuntimeError("OCR dependencies not installed. Install pytesseract, pdf2image, Pillow")
	
	# Convert PDF pages to images
	try:
		images = convert_from_path(str(pdf_path), dpi=150)
	except Exception as e:
		raise RuntimeError(f"pdf2image conversion failed: {e}")
	
	pages = []
	for img in images:
		width, height = img.size
		page_info = {"width": float(width), "height": float(height), "blocks": []}
		
		# Run OCR with bounding box data
		try:
			ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang='eng')
		except Exception as e:
			# OCR failed for this page, skip
			pages.append(page_info)
			continue
		
		# Group words into blocks (by line/paragraph)
		# Simple heuristic: group consecutive words with similar y-coordinates
		current_block = {"words": [], "bbox": [None, None, None, None], "text": ""}
		blocks_list = []
		
		for i in range(len(ocr_data['text'])):
			text = ocr_data['text'][i].strip()
			if not text:
				continue
			conf = int(ocr_data['conf'][i])
			if conf < 30:  # Skip low-confidence text
				continue
			
			x, y, w, h = ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i]
			word_bbox = [x, y, x + w, y + h]
			
			# Check if this word is part of current block (similar y-coordinate)
			if current_block["bbox"][0] is None:
				# First word in block
				current_block["bbox"] = word_bbox
				current_block["words"].append(text)
			else:
				# Check vertical distance
				prev_y = current_block["bbox"][1]
				if abs(y - prev_y) < 15:  # Same line/block (tolerance: 15px)
					# Extend block bbox
					current_block["bbox"][0] = min(current_block["bbox"][0], word_bbox[0])
					current_block["bbox"][1] = min(current_block["bbox"][1], word_bbox[1])
					current_block["bbox"][2] = max(current_block["bbox"][2], word_bbox[2])
					current_block["bbox"][3] = max(current_block["bbox"][3], word_bbox[3])
					current_block["words"].append(text)
				else:
					# New block
					if current_block["words"]:
						current_block["text"] = " ".join(current_block["words"])
						blocks_list.append(current_block)
					current_block = {"words": [text], "bbox": word_bbox, "text": ""}
		
		# Add last block
		if current_block["words"]:
			current_block["text"] = " ".join(current_block["words"])
			blocks_list.append(current_block)
		
		# Convert to page format
		for b in blocks_list:
			bbox = b["bbox"]
			if bbox[0] is not None:
				page_info["blocks"].append({
					"bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
					"text": b["text"],
					"font_size": 12.0  # default
				})
		
		pages.append(page_info)
	
	return {"pages": pages}


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
	import cv2  # type: ignore
	import numpy as np  # type: ignore
	_cv_available = True
except Exception:
	cv2 = None  # type: ignore
	np = None  # type: ignore
	_cv_available = False

try:
	import pytesseract
	from pdf2image import convert_from_path
	from PIL import Image, ImageDraw, ImageFont
except Exception:
	pytesseract = None  # type: ignore
	convert_from_path = None  # type: ignore
	Image = None  # type: ignore
	ImageDraw = None  # type: ignore
	ImageFont = None  # type: ignore

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



def _compute_iou(bbox1: list, bbox2: list) -> float:
	"""
	Compute Intersection over Union (IoU) of two bounding boxes.
	bbox: [x0, y0, x1, y1]
	"""
	x0_1, y0_1, x1_1, y1_1 = bbox1
	x0_2, y0_2, x1_2, y1_2 = bbox2
	
	# Intersection
	ix0 = max(x0_1, x0_2)
	iy0 = max(y0_1, y0_2)
	ix1 = min(x1_1, x1_2)
	iy1 = min(y1_1, y1_2)
	
	if ix1 <= ix0 or iy1 <= iy0:
		return 0.0
	
	intersection = (ix1 - ix0) * (iy1 - iy0)
	area1 = (x1_1 - x0_1) * (y1_1 - y0_1)
	area2 = (x1_2 - x0_2) * (y1_2 - y0_2)
	union = area1 + area2 - intersection
	
	if union <= 0:
		return 0.0
	
	return intersection / union


def _text_similarity(text1: str, text2: str) -> float:
	"""
	Compute text similarity ratio (0.0 to 1.0).
	"""
	t1 = text1.strip().lower()
	t2 = text2.strip().lower()
	if not t1 or not t2:
		return 0.0
	
	# Check exact match
	if t1 == t2:
		return 1.0
	
	# Check substring
	if t1 in t2 or t2 in t1:
		return max(len(t1), len(t2)) / max(len(t1), len(t2))
	
	# Character-level similarity
	from difflib import SequenceMatcher
	return SequenceMatcher(None, t1, t2).ratio()


def _merge_spans_in_line(spans: list) -> tuple[str, float, float]:
	"""
	Merge spans within a line into text, handling soft hyphens correctly.
	Returns (merged_text, line_x0, median_font_size)
	"""
	if not spans:
		return "", 0.0, 0.0
	
	text_parts = []
	sizes = []
	x0_min = None
	
	for span in spans:
		text = span.get("text", "") or ""
		if not text:
			continue
		
		# Remove soft hyphens (Unicode U+00AD)
		text = text.replace("\u00ad", "")
		
		text_parts.append(text)
		
		size = span.get("size", 0.0) or 0.0
		if size > 0:
			sizes.append(float(size))
		
		bbox = span.get("bbox")
		if bbox and len(bbox) == 4:
			sx0 = float(bbox[0])
			if x0_min is None or sx0 < x0_min:
				x0_min = sx0
	
	merged_text = "".join(text_parts)
	
	# Handle hyphenation at end of line
	# Remove trailing hyphen if it's a word break
	if merged_text.endswith("-") and len(merged_text) > 1:
		# Keep hyphen if it's part of a compound word (preceded by alphanumeric)
		if merged_text[-2].isalnum():
			merged_text = merged_text[:-1]  # Remove hyphen for word continuation
	
	median_size = 0.0
	if sizes:
		sizes_sorted = sorted(sizes)
		mid = len(sizes_sorted) // 2
		if len(sizes_sorted) % 2 == 0:
			median_size = (sizes_sorted[mid - 1] + sizes_sorted[mid]) / 2.0
		else:
			median_size = sizes_sorted[mid]
	
	return merged_text, x0_min or 0.0, median_size


def _detect_bullet_list(text: str) -> bool:
	"""
	Detect if text starts with a bullet/list marker.
	"""
	if not text:
		return False
	
	stripped = text.lstrip()
	if not stripped:
		return False
	
	# Common bullet characters
	bullet_chars = ['•', '◦', '▪', '▫', '–', '—', '●', '○', '■', '□', '‣', '⁃', '*', '·']
	
	if stripped[0] in bullet_chars:
		return True
	
	# Numbered lists: 1. 2. 3. etc.
	import re
	if re.match(r'^\d{1,3}[\.\)]\s', stripped):
		return True
	
	# Lettered lists: a. b. c. A. B. C.
	if re.match(r'^[a-zA-Z][\.\)]\s', stripped):
		return True
	
	# Roman numerals: i. ii. iii. I. II. III.
	if re.match(r'^[ivxIVX]{1,5}[\.\)]\s', stripped):
		return True
	
	return False


def _segment_columns(blocks: list, page_width: float) -> list[list]:
	"""
	Segment blocks into columns using X-coordinate clustering.
	Returns list of column blocks, sorted left to right.
	"""
	if not blocks:
		return []
	
	# Extract x-intervals for each block
	intervals = []
	for block in blocks:
		x0, y0, x1, y1 = block["bbox"]
		intervals.append((x0, x1, block))
	
	# Sort by x0
	intervals.sort(key=lambda iv: iv[0])
	
	# Find column breaks using gap detection
	# A gap larger than 10% of page width indicates column boundary
	gap_threshold = page_width * 0.10
	
	columns = []
	current_column = []
	prev_x1 = None
	
	for x0, x1, block in intervals:
		if prev_x1 is not None and (x0 - prev_x1) > gap_threshold:
			# Start new column
			if current_column:
				columns.append(current_column)
			current_column = [block]
		else:
			current_column.append(block)
		
		prev_x1 = max(prev_x1, x1) if prev_x1 is not None else x1
	
	if current_column:
		columns.append(current_column)
	
	# Sort each column by Y coordinate (top to bottom)
	for col in columns:
		col.sort(key=lambda b: b["bbox"][1])
	
	return columns


def _group_lines_into_paragraphs(lines: list, page_height: float) -> list[dict]:
	"""
	Group lines into paragraph-level blocks based on:
	- Line height (font size)
	- Y-gap between lines
	- Indentation (X-offset)
	- Bullet detection
	
	Returns list of paragraph blocks.
	"""
	if not lines:
		return []
	
	paragraphs = []
	current_para = None
	
	for i, line in enumerate(lines):
		bbox = line["bbox"]
		text = line["text"]
		font_size = line["font_size"]
		x0 = line["line_x0"]
		
		y0, y1 = bbox[1], bbox[3]
		line_height = y1 - y0
		
		# Determine if this line starts a new paragraph
		start_new_para = False
		
		if current_para is None:
			start_new_para = True
		else:
			prev_line = current_para["lines"][-1]
			prev_y1 = prev_line["bbox"][3]
			prev_x0 = prev_line["line_x0"]
			prev_font_size = prev_line["font_size"]
			prev_height = prev_line["bbox"][3] - prev_line["bbox"][1]
			
			y_gap = y0 - prev_y1
			avg_height = (line_height + prev_height) / 2.0
			
			# Large vertical gap -> new paragraph
			if y_gap > avg_height * 0.6:
				start_new_para = True
			
			# Significant indentation change -> new paragraph
			indent_change = abs(x0 - prev_x0)
			if indent_change > 15:
				start_new_para = True
			
			# Bullet list item -> new paragraph
			if _detect_bullet_list(text):
				start_new_para = True
			
			# Font size change -> new paragraph (likely heading or different section)
			if abs(font_size - prev_font_size) > 1.5:
				start_new_para = True
		
		if start_new_para:
			if current_para is not None:
				paragraphs.append(current_para)
			
			current_para = {
				"lines": [line],
				"bbox": bbox[:],
				"font_size": font_size,
				"is_bullet": _detect_bullet_list(text)
			}
		else:
			# Extend current paragraph
			current_para["lines"].append(line)
			# Update bounding box
			pbbox = current_para["bbox"]
			current_para["bbox"] = [
				min(pbbox[0], bbox[0]),
				min(pbbox[1], bbox[1]),
				max(pbbox[2], bbox[2]),
				max(pbbox[3], bbox[3])
			]
	
	if current_para is not None:
		paragraphs.append(current_para)
	
	return paragraphs


def _merge_paragraph_text(paragraph: dict) -> str:
	"""
	Merge lines within a paragraph into final text.
	Handle soft hyphens and line breaks properly.
	"""
	lines = paragraph.get("lines", [])
	if not lines:
		return ""
	
	text_parts = []
	
	for i, line in enumerate(lines):
		text = line["text"]
		
		if i == len(lines) - 1:
			# Last line - add as is
			text_parts.append(text)
		else:
			# Not last line - check for hyphenation
			if text.endswith("-"):
				# Word continues on next line
				text_parts.append(text[:-1])
			elif text.endswith((".", "!", "?", ":", ";")):
				# Sentence ends - add newline
				text_parts.append(text + "\n")
			else:
				# Normal continuation - add space
				text_parts.append(text + " ")
	
	return "".join(text_parts).strip()


def extract_layout_blocks(pdf_path: Path):
	"""
	Extract page sizes and text blocks using industry-standard approach.
	
	Pipeline:
	1. Extract lines from rawdict (span-level precision)
	2. Merge lines into paragraphs (line height, indent, y-gap based)
	3. Segment into columns (X-interval clustering)
	4. Sort in true reading order (column-wise, top to bottom)
	5. Suppress duplicates (IoU + text similarity)
	6. Merge dict blocks for completeness
	
	Returns:
	{
	  "pages": [
	    {
	      "width": float, "height": float,
	      "blocks": [
	        {"bbox": [x0,y0,x1,y1], "text": "...", "font_size": 12.3, "text_start_x": x0}
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
	
	for page_num, page in enumerate(doc):
		page_width = float(page.rect.width)
		page_height = float(page.rect.height)
		page_info = {"width": page_width, "height": page_height, "blocks": []}
		
		# Step 1: Extract all lines from rawdict with span-level detail
		raw = page.get_text("rawdict")
		lines = []
		
		for block in raw.get("blocks", []):
			if block.get("type") != 0:  # Skip non-text blocks
				continue
			
			for line in block.get("lines", []):
				spans = line.get("spans", [])
				if not spans:
					continue
				
				# Merge spans into line text
				line_text, line_x0, median_font_size = _merge_spans_in_line(spans)
				
				if not line_text.strip():
					continue
				
				# Compute line bounding box
				line_bbox = line.get("bbox")
				if not line_bbox or len(line_bbox) != 4:
					continue
				
				x0, y0, x1, y1 = [float(v) for v in line_bbox]
				
				lines.append({
					"bbox": [x0, y0, x1, y1],
					"text": line_text.strip(),
					"font_size": median_font_size,
					"line_x0": line_x0
				})
		
		# Step 2: Group lines into paragraphs
		paragraphs = _group_lines_into_paragraphs(lines, page_height)
		
		# Step 3: Convert paragraphs to blocks
		raw_blocks = []
		for para in paragraphs:
			text = _merge_paragraph_text(para)
			if not text.strip():
				continue
			
			raw_blocks.append({
				"bbox": para["bbox"],
				"text": text,
				"font_size": para["font_size"],
				"text_start_x": para["lines"][0]["line_x0"] if para["lines"] else para["bbox"][0],
				"is_bullet": para.get("is_bullet", False)
			})
		
		# Step 4: Add dict blocks for any missing text (e.g., text in images)
		dict_data = page.get_text("dict")
		if dict_data and "blocks" in dict_data:
			for block in dict_data.get("blocks", []):
				if block.get("type") != 0:
					continue
				
				bbox = block.get("bbox")
				if not bbox or len(bbox) != 4:
					continue
				
				lines_in_block = block.get("lines", [])
				if not lines_in_block:
					continue
				
				# Extract text from dict block
				text_parts = []
				font_sizes = []
				for line in lines_in_block:
					line_text, _, font_size = _merge_spans_in_line(line.get("spans", []))
					if line_text.strip():
						text_parts.append(line_text.strip())
						if font_size > 0:
							font_sizes.append(font_size)
				
				if not text_parts:
					continue
				
				block_text = " ".join(text_parts)
				median_font_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 12.0
				
				# Check if this block is a duplicate of existing blocks
				is_duplicate = False
				for existing in raw_blocks:
					iou = _compute_iou(bbox, existing["bbox"])
					text_sim = _text_similarity(block_text, existing["text"])
					
					# Duplicate if high IoU and high text similarity
					if iou > 0.7 or (iou > 0.3 and text_sim > 0.8):
						is_duplicate = True
						break
				
				if not is_duplicate:
					raw_blocks.append({
						"bbox": [float(v) for v in bbox],
						"text": block_text,
						"font_size": median_font_size,
						"text_start_x": float(bbox[0]),
						"is_bullet": _detect_bullet_list(block_text)
					})
		
		# Step 5: Segment into columns
		columns = _segment_columns(raw_blocks, page_width)
		
		# Step 6: Sort in true reading order (left to right columns, top to bottom within column)
		ordered_blocks = []
		for column in columns:
			# Within each column, already sorted by Y in _segment_columns
			ordered_blocks.extend(column)
		
		# Step 7: Final duplicate suppression using IoU + text similarity
		final_blocks = []
		for block in ordered_blocks:
			is_duplicate = False
			
			for existing in final_blocks:
				iou = _compute_iou(block["bbox"], existing["bbox"])
				text_sim = _text_similarity(block["text"], existing["text"])
				
				# Suppress if:
				# - Very high IoU (>0.8) OR
				# - Medium IoU (>0.5) + high text similarity (>0.85)
				if iou > 0.8 or (iou > 0.5 and text_sim > 0.85):
					is_duplicate = True
					break
			
			if not is_duplicate:
				# Clean up block for output
				final_blocks.append({
					"bbox": block["bbox"],
					"text": block["text"],
					"font_size": block["font_size"],
					"text_start_x": block.get("text_start_x", block["bbox"][0])
				})
		
		page_info["blocks"] = final_blocks
		pages.append(page_info)
		
		num_cols = len(columns)
		print(f"Page {page_num + 1}: Extracted {len(lines)} lines → {len(paragraphs)} paragraphs → {len(final_blocks)} blocks in {num_cols} column(s)")
	
	doc.close()
	return {"pages": pages}


def _is_image_region(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> bool:
	"""
	Check if a region contains complex image/graphics (not simple text background).
	Returns True if the region is an image area.
	"""
	if not _cv_available:
		return False
	try:
		h, w = img.shape[:2]
		x0 = max(0, min(x0, w - 1))
		y0 = max(0, min(y0, h - 1))
		x1 = max(x0 + 1, min(x1, w))
		y1 = max(y0 + 1, min(y1, h))
		
		if x1 <= x0 or y1 <= y0:
			return False
		
		region = img[y0:y1, x0:x1]
		if region.size == 0:
			return False
		
		# Convert to grayscale if needed
		if len(region.shape) == 3:
			gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)  # type: ignore
		else:
			gray = region
		
		# Calculate statistics
		mean_val = float(np.mean(gray))  # type: ignore
		std_val = float(np.std(gray))  # type: ignore
		min_val = float(np.min(gray))  # type: ignore
		max_val = float(np.max(gray))  # type: ignore
		brightness_range = max_val - min_val
		variance = std_val * std_val
		
		# Image detection criteria:
		# 1. High variance (> 150) - complex patterns
		# 2. Wide brightness range (> 80) - diverse colors
		# 3. Dark background with variance (> 50) - dark images
		is_dark = mean_val < 120
		is_complex = variance > 150 or brightness_range > 80 or (is_dark and variance > 50) or brightness_range > 60
		
		return is_complex
	except Exception:
		return False


def _upscale_image_super_resolution(img: np.ndarray, scale_factor: float = 2.0) -> np.ndarray:
	"""
	Upscale image using high-quality interpolation (Lanczos4).
	For better results, could use DNN-based super-resolution (EDSR/Real-ESRGAN) later.
	"""
	if not _cv_available:
		return img
	
	# Use Lanczos4 interpolation for high-quality upscaling
	# This is better than cubic interpolation for preserving details
	new_width = int(img.shape[1] * scale_factor)
	new_height = int(img.shape[0] * scale_factor)
	upscaled = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)  # type: ignore
	return upscaled


def _detect_text_color(img: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int]:
	"""
	Detect original text color from image region.
	Returns RGB tuple (0-255, 0-255, 0-255).
	Uses edge detection to find text pixels more accurately.
	"""
	try:
		h, w = img.shape[:2]
		x0 = max(0, min(x0, w - 1))
		y0 = max(0, min(y0, h - 1))
		x1 = max(x0 + 1, min(x1, w))
		y1 = max(y0 + 1, min(y1, h))
		
		region = img[y0:y1, x0:x1]
		if region.size == 0:
			return (0, 0, 0)  # Default to black
		
		# Convert to grayscale for analysis
		if len(region.shape) == 3:
			if region.shape[2] == 3:
				# BGR to grayscale
				gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)  # type: ignore
			else:
				gray = region[:, :, 0]
		else:
			gray = region
		
		# Use edge detection to find text pixels
		edges = cv2.Canny(gray, 50, 150)  # type: ignore
		edge_pixels = gray[edges > 0]
		
		if len(edge_pixels) == 0:
			# No edges found, use mean of entire region
			mean_brightness = float(np.mean(gray))  # type: ignore
		else:
			# Use edge pixels (likely text) to determine color
			mean_brightness = float(np.mean(edge_pixels))  # type: ignore
		
		# Determine if text is light or dark
		# Lower threshold to prefer black text (more common)
		if mean_brightness > 180:
			# Very light pixels - likely white text on dark background
			return (255, 255, 255)
		else:
			# Dark or medium pixels - likely black text on light background
			return (0, 0, 0)
	except Exception as e:
		print(f"Error detecting text color: {e}")
		return (0, 0, 0)  # Default to black


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
	"""
	Wrap text to fit within max_width using font metrics.
	Supports both word-based (for English) and character-based (for Korean) wrapping.
	Returns list of lines.
	"""
	if not text:
		return []
	
	# Check if text contains Korean characters
	has_korean = any('\uAC00' <= char <= '\uD7A3' for char in text)
	
	if has_korean:
		# Character-based wrapping for Korean text
		lines = []
		current_line = []
		current_width = 0
		
		for char in text:
			# Test if adding this character would exceed width
			test_line = "".join(current_line) + char
			bbox = font.getbbox(test_line)
			char_width = bbox[2] - bbox[0]
			
			# If adding this character exceeds width and we have content, start new line
			if char_width > max_width and current_line:
				# Save current line
				lines.append("".join(current_line))
				current_line = [char]
				# Recalculate width for new line
				bbox = font.getbbox(char)
				current_width = bbox[2] - bbox[0]
			else:
				current_line.append(char)
				current_width = char_width
		
		# Add last line
		if current_line:
			lines.append("".join(current_line))
		
		return lines if lines else [text]
	else:
		# Word-based wrapping for English text
		words = text.split()
		if not words:
			return [text]
		
		lines = []
		current_line = []
		current_width = 0
		
		for word in words:
			# Add space if not first word
			test_text = " ".join(current_line + [word]) if current_line else word
			bbox = font.getbbox(test_text)
			word_width = bbox[2] - bbox[0]
			
			if current_width + word_width <= max_width or not current_line:
				current_line.append(word)
				current_width = word_width
			else:
				lines.append(" ".join(current_line))
				current_line = [word]
				current_width = font.getbbox(word)[2] - font.getbbox(word)[0]
		
		if current_line:
			lines.append(" ".join(current_line))
		
		return lines if lines else [text]


def _calculate_alignment_offset(
	line_width: float,
	available_width: float,
	text_start_x: float,
	bbox_x0: float,
	bbox_x1: float,
) -> float:
	"""
	원본 text_start_x를 기반으로 정렬 방식(left/center/right)을 추정하고
	해당 정렬을 유지하도록 x 오프셋을 계산한다.
	"""
	bbox_width = bbox_x1 - bbox_x0
	if bbox_width <= 0 or available_width <= 0 or line_width >= available_width:
		return 0.0
	
	# 원본에서 텍스트 시작 위치가 bbox 안에서 어느 정도 비율인지 계산
	original_offset = text_start_x - bbox_x0
	ratio = original_offset / bbox_width if bbox_width > 0 else 0.0
	
	# 절대적인 픽셀 기준도 함께 사용 (스케일 편차 보정)
	abs_offset = max(0.0, original_offset)
	
	# 대략적인 정렬 타입 결정
	# 1) 거의 왼쪽에 붙어 있는 경우 (좌측 정렬)
	if abs_offset < 8 or original_offset < bbox_width * 0.25:
		# 좌측 정렬
		return 0.0
	# 2) 중앙 주변
	elif bbox_width * 0.35 <= original_offset <= bbox_width * 0.65:
		return max(0.0, (available_width - line_width) / 2.0)
	# 3) 거의 오른쪽에 붙어 있는 경우 (우측 정렬)
	elif original_offset > bbox_width * 0.8 or abs_offset > bbox_width - 10:
		return max(0.0, available_width - line_width)
	
	# 그 외의 경우, 원본 비율을 유지하도록 비례 배치
	target = ratio * available_width
	# target 위치가 라인의 중앙에 오도록 보정
	return max(0.0, min(available_width - line_width, target - line_width / 2.0))


def _render_block_text(
	block: dict,
	draw: ImageDraw.ImageDraw,
	img_original: np.ndarray,
	korean_font_path: Optional[str],
	rendered_areas: list[tuple[float, float, float, float]],
	min_block_spacing: int,
	page_index: int,
	block_index: int,
	page_height: int,
	page_width: int,
) -> Optional[tuple[float, float, float, float]]:
	"""
	하나의 텍스트 블록을 고품질로 렌더링한다.
	- Character-level wrapping (Korean) / word-level (English)
	- block 높이에 맞게 폰트 크기 자동 조절
	- 기존 정렬(text_start_x)을 최대한 유지
	- 이전 블록들과 충돌하면 y 좌표를 아래로 자동 재배치
	- line_height는 font height * 2.2 배로 넉넉하게
	"""
	x0, y0, x1, y1 = block["bbox"]
	text = (block.get("text") or "").strip()
	if not text:
		return None
	
	original_font_size = max(8, int(block.get("font_size", 12)))
	text_start_x = float(block.get("text_start_x", x0))
	
	block_width = x1 - x0
	if block_width <= 4:
		print(f"Page {page_index + 1}, Block {block_index}: too small -> skip")
		return None
	
	# 텍스트 색상 감지 (원본 이미지 기준)
	text_color = _detect_text_color(img_original, int(x0), int(y0), int(x1), int(y1))
	
	# 페이지 전체 폭 기준 고정 column 사용 (한국어가 길어도 잘리지 않게)
	COMMON_LEFT = int(page_width * 0.10)  # 페이지 왼쪽 10%
	COMMON_RIGHT = int(page_width * 0.90)  # 페이지 오른쪽 90%
	available_width = COMMON_RIGHT - COMMON_LEFT
	
	# 내부 margin 설정 (픽셀)
	v_margin = max(2, int(original_font_size * 0.10))
	# 높이는 페이지 하단까지 전체를 사용 (블록 높이에 제한 두지 않음)
	available_height = max(0.0, page_height - (y0 + v_margin))
	if available_width <= 0 or available_height <= 0:
		print(f"Page {page_index + 1}, Block {block_index}: no available area")
		return None
	
	# 폰트 로드
	def load_font(size: int) -> ImageFont.FreeTypeFont:
		try:
			if korean_font_path and korean_font_path.endswith(".ttc"):
				return ImageFont.truetype(korean_font_path, size)
			if korean_font_path and korean_font_path.endswith(".ttf"):
				return ImageFont.truetype(korean_font_path, size)
		except Exception as e:
			print(f"Page {page_index + 1}, Block {block_index}: font load failed -> {e}")
		return ImageFont.load_default()
	
	# 원본 폰트 크기를 기준으로, 한국어가 더 길 수 있으므로 80~90% 정도로 시작
	font_size = int(original_font_size * 0.85)
	min_font_size = max(7, int(original_font_size * 0.4))
	font = load_font(font_size)
	
	line_height = 0.0
	
	# 폰트 크기 반복 조절해 블록 안에 전체 텍스트를 fit
	for _ in range(8):
		lines = _wrap_text(text, font, int(available_width))
		if not lines:
			return None
		
		# line height 계산: 원본에 맞게 더 타이트하게 (1.35배)
		try:
			ascent, descent = font.getmetrics()
			base_height = ascent + descent
			line_height = base_height * 1.35
		except Exception:
			try:
				bbox = font.getbbox("한글Ag")
				base_height = bbox[3] - bbox[1]
				line_height = base_height * 1.35
			except Exception:
				line_height = font_size * 1.35
		
		total_height = line_height * len(lines)
		if total_height <= available_height:
			break
		
		# fit 되지 않으면 폰트 크기 줄이기
		scale = (available_height / total_height) * 0.92  # 약간 여유를 둠
		new_size = max(min_font_size, int(font_size * scale))
		if new_size >= font_size:
			# 더 줄일 수 없으면 현재 상태 사용
			break
		font_size = new_size
		font = load_font(font_size)
	else:
		# 반복 후에도 맞지 않으면 마지막 상태 사용
		lines = _wrap_text(text, font, int(available_width))
		try:
			ascent, descent = font.getmetrics()
			base_height = ascent + descent
			line_height = base_height * 1.35
		except Exception:
			line_height = font_size * 1.35
	
	if not lines:
		return None
	
	# 기존 블록들과의 충돌을 피하도록 y 위치 조정
	actual_y0 = y0 + v_margin
	MIN_SPACING = max(15, min_block_spacing)
	for prev_x0, prev_y0, prev_x1, prev_y1 in rendered_areas:
		# 수평으로 일정 부분 이상 겹치면 같은 column 이라고 가정
		h_overlap = not (x1 < prev_x0 - 5 or x0 > prev_x1 + 5)
		if not h_overlap:
			continue
		# 이전에 렌더링된 어떤 블록과도 겹치지 않도록,
		# 해당 블록의 하단(prev_y1)보다 최소 한 줄(line_height) 이상 아래에서 시작
		required = max(MIN_SPACING, int(line_height))
		if actual_y0 < prev_y1 + required:
			actual_y0 = prev_y1 + required
	
	# 최종 높이 검증, 필요시 일부 줄만 출력 (페이지 하단 기준)
	max_height = page_height - v_margin - actual_y0
	if max_height <= 0:
		return None
	max_lines = min(len(lines), int(max_height // line_height))
	if max_lines <= 0:
		return None
	if max_lines < len(lines):
		print(
			f"Page {page_index + 1}, Block {block_index}: "
			f"clipping lines {max_lines}/{len(lines)} due to page bottom"
		)
		lines = lines[:max_lines]
	
	# 실제 렌더링
	current_y = actual_y0
	rendered_x0 = x1
	rendered_x1 = x0
	first_line_y = current_y
	last_line_y = current_y
	
	for line in lines:
		if not line.strip():
			current_y += line_height
			continue
		
		# 라인 폭 계산
		try:
			lbbox = font.getbbox(line)
			line_width = lbbox[2] - lbbox[0]
		except Exception:
			line_width = len(line) * font_size * 0.6
		
		# 페이지 하단을 넘기면 중단 (line_height는 고정) - 블록 bbox가 아니라 페이지 전체 기준
		if current_y + line_height > page_height - v_margin:
			break
		
		# 고정 column 시작점(COMMON_LEFT)에서 시작
		text_x = float(COMMON_LEFT)
		# 오른쪽이 잘리면 왼쪽 정렬 유지
		if text_x + line_width > COMMON_RIGHT:
			# 줄 전체가 column을 넘어가면, 왼쪽부터 시작해서 오른쪽까지만 표시
			text_x = float(COMMON_LEFT)
		
		try:
			draw.text((int(text_x), int(current_y)), line, fill=text_color, font=font)
		except Exception as e:
			print(f"Page {page_index + 1}, Block {block_index}: draw failed -> {e}")
			break
		
		rendered_x0 = min(rendered_x0, text_x)
		rendered_x1 = max(rendered_x1, text_x + line_width)
		last_line_y = current_y + line_height
		current_y += line_height
	
	if last_line_y <= first_line_y:
		return None
	
	# 다음 블록을 위한 여유 공간 포함한 영역 반환
	extra_spacing = max(MIN_SPACING, int(line_height * 0.7))
	return (
		rendered_x0 - 2,
		first_line_y - 2,
		rendered_x1 + 2,
		last_line_y + extra_spacing,
	)


def render_high_quality_preview_images(
	pdf_path: Path, 
	layout: dict, 
	out_dir: Path, 
	text_overlay_dir: Path,
	dpi: int = 300,
	upscale_factor: float = 1.5
) -> List[Path]:
	"""
	Render high-quality preview images with inpaint and Korean text rendering.
	- Renders at high DPI
	- Upscales using super-resolution techniques
	- Removes original text using inpaint
	- Renders Korean translated text directly on image using Pillow
	- Detects original text color and uses it for Korean text
	- Handles line breaks automatically
	
	Returns list of output image paths.
	"""
	if fitz is None:
		raise RuntimeError("PyMuPDF(fitz)가 설치되어 있지 않습니다.")
	if Image is None or ImageDraw is None or ImageFont is None:
		raise RuntimeError("Pillow가 설치되어 있지 않습니다.")
	
	out_dir.mkdir(parents=True, exist_ok=True)
	text_overlay_dir.mkdir(parents=True, exist_ok=True)
	doc = fitz.open(str(pdf_path))
	output_paths: List[Path] = []
	
	# High DPI rendering for better quality
	zoom = dpi / 72.0
	matrix = fitz.Matrix(zoom, zoom)
	
	for page_index, page in enumerate(doc):
		# Render at high DPI
		pix = page.get_pixmap(matrix=matrix, alpha=False)
		
		# Convert to numpy image
		if _cv_available:
			img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))  # type: ignore
			# Convert RGB to BGR for OpenCV
			if pix.n == 3:
				img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # type: ignore
			elif pix.n == 4:
				img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)  # type: ignore
			
			# Apply super-resolution upscaling
			if upscale_factor > 1.0:
				img = _upscale_image_super_resolution(img, upscale_factor)
			
			h, w = img.shape[:2]
			
			# Save original image for color detection (before inpaint)
			img_original = img.copy()
			
			# Build mask for text blocks (excluding image regions)
			mask = np.zeros((h, w), dtype=np.uint8)  # type: ignore
			text_blocks = []
			
			try:
				pages = layout.get("pages", [])
				if page_index < len(pages):
					page_layout = pages[page_index]
					lw = float(page_layout.get("width", w / upscale_factor))
					lh = float(page_layout.get("height", h / upscale_factor))
					sx = w / lw if lw else 1.0
					sy = h / lh if lh else 1.0
					
					total_blocks = len(page_layout.get("blocks", []))
					image_blocks_skipped = 0
					empty_blocks_skipped = 0
					
					for b in page_layout.get("blocks", []):
						x0, y0, x1, y1 = b.get("bbox", [0, 0, 0, 0])
						rx0 = max(0, int(x0 * sx))
						ry0 = max(0, int(y0 * sy))
						rx1 = min(w - 1, int(x1 * sx))
						ry1 = min(h - 1, int(y1 * sy))
						
						# 1) 이미지 영역 감지: 이미지 위에 있는 텍스트는 렌더링하지 않음
						if _is_image_region(img, rx0, ry0, rx1, ry1):
							image_blocks_skipped += 1
							# inpaint 마스크에서는 그대로 지워서 원본 영어를 제거
							padding = 1
							mask_x0 = max(0, rx0 - padding)
							mask_y0 = max(0, ry0 - padding)
							mask_x1 = min(w - 1, rx1 + padding)
							mask_y1 = min(h - 1, ry1 + padding)
							cv2.rectangle(mask, (mask_x0, mask_y0), (mask_x1, mask_y1), color=255, thickness=-1)  # type: ignore
							continue
						
						# 2) 일반 텍스트 영역: inpaint 마스크 + 렌더링용 text_blocks 모두 구성
						padding = 1
						mask_x0 = max(0, rx0 - padding)
						mask_y0 = max(0, ry0 - padding)
						mask_x1 = min(w - 1, rx1 + padding)
						mask_y1 = min(h - 1, ry1 + padding)
						cv2.rectangle(mask, (mask_x0, mask_y0), (mask_x1, mask_y1), color=255, thickness=-1)  # type: ignore
						
						# Store text block info for rendering
						translated_text = b.get("translated_text") or ""
						original_text = b.get("text", "")
						
						# If translated_text is missing but original_text exists, try to translate it
						if not translated_text.strip() and original_text.strip():
							# Fallback: translate the original text on the fly
							try:
								from ..services.translate_service import translate_text
								print(f"Page {page_index + 1}: Missing translation for block, translating on-the-fly: '{original_text[:100]}...'")
								translated_text = translate_text(original_text.strip(), target_lang="ko")
								if translated_text.strip():
									print(f"Page {page_index + 1}: Translated block on-the-fly: '{original_text[:50]}...' -> '{translated_text[:50]}...'")
								else:
									print(f"Page {page_index + 1}: Warning: Translation returned empty, using original text")
									translated_text = original_text
							except Exception as e:
								print(f"Page {page_index + 1}: Failed to translate block on-the-fly: {e}")
								import traceback
								traceback.print_exc()
								# Use original text as fallback (better than skipping)
								translated_text = original_text
						
						# Only skip if both original and translated are empty
						if not translated_text.strip() and not original_text.strip():
							empty_blocks_skipped += 1
							print(f"Page {page_index + 1}: Skipping empty block at ({x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f})")
							continue
						
						# If translated_text is still empty but original_text exists, use original as last resort
						if not translated_text.strip() and original_text.strip():
							print(f"Page {page_index + 1}: Warning: Using original text as fallback for block: '{original_text[:50]}...'")
							translated_text = original_text
						
						# Get original text start position for alignment
						original_text_start_x = b.get("text_start_x", x0)
						scaled_text_start_x = original_text_start_x * sx
						
						text_blocks.append({
							"bbox": [rx0, ry0, rx1, ry1],
							"text": translated_text,
							"font_size": b.get("font_size", 12) * (sx + sy) / 2,
							"original_bbox": [x0, y0, x1, y1],
							"text_start_x": scaled_text_start_x
						})
					
					print(f"Page {page_index + 1}: Total blocks: {total_blocks}, Image blocks skipped: {image_blocks_skipped}, Empty blocks skipped: {empty_blocks_skipped}, Text blocks to render: {len(text_blocks)}")
			except Exception as e:
				print(f"Error processing text blocks for page {page_index}: {e}")
				import traceback
				traceback.print_exc()
			
			# Apply inpaint to remove original text - minimal processing to reduce blur
			if mask.any():  # type: ignore
				# Use mask directly without dilation for minimal blur
				radius = 1
				img = cv2.inpaint(img, mask, radius, cv2.INPAINT_TELEA)  # type: ignore
			
			# Convert BGR to RGB for Pillow
			img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # type: ignore
			pil_img = Image.fromarray(img_rgb)
			draw = ImageDraw.Draw(pil_img)
			
			# Load Korean font
			korean_font_path = None
			try:
				korean_font_path = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"
				base_font = ImageFont.truetype(korean_font_path, 24)
			except:
				try:
					korean_font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
					base_font = ImageFont.truetype(korean_font_path, 24)
				except:
					korean_font_path = None
					base_font = ImageFont.load_default()
			
			# Render Korean text on image with spacing to avoid overlap
			print(f"Page {page_index + 1}: Rendering {len(text_blocks)} text blocks")
			
			# Sort blocks by y position (top to bottom) to handle overlaps
			sorted_blocks = sorted(enumerate(text_blocks), key=lambda item: (item[1]["bbox"][1], item[1]["bbox"][0]))
			
			# Track rendered text areas to avoid overlaps
			rendered_areas: list[tuple[float, float, float, float]] = []  # (x0, y0, x1, y1)
			# 전체 블록의 폰트 크기를 기반으로 "본문" 기준 크기 추정
			# → 가장 작은 본문 폰트 크기(min)를 기준으로 통일하면
			#   캡션/본문이 섞여 있어도 과도하게 큰 글씨를 피할 수 있다.
			base_font_size = 12
			if text_blocks:
				all_sizes = [int(b.get("font_size", 12)) for b in text_blocks]
				if all_sizes:
					base_font_size = min(all_sizes)
			
			# 제목(헤드라인)과 본문을 구분: base_font_size보다 충분히 큰 경우만 제목으로 간주
			title_threshold = base_font_size * 1.4
			
			# 본문 블록들의 공통 시작 x 좌표(컬럼 왼쪽)를 계산하여 정렬 맞추기
			body_start_xs: list[float] = []
			for b in text_blocks:
				fs = float(b.get("font_size", base_font_size))
				if fs < title_threshold:
					ts = float(b.get("text_start_x", b["bbox"][0]))
					body_start_xs.append(ts)
			common_body_start_x = min(body_start_xs) if body_start_xs else None
			
			for b in text_blocks:
				fs = float(b.get("font_size", base_font_size))
				# 본문/캡션: 모두 동일한 본문 폰트 크기로 정규화 + 시작 x를 공통 컬럼으로 통일
				if fs < title_threshold:
					b["font_size"] = float(base_font_size)
					if common_body_start_x is not None:
						b["text_start_x"] = float(common_body_start_x)
				else:
					# 제목: 과도하게 크지 않도록 상한선(clamp) 적용
					max_title_size = base_font_size * 1.6
					b["font_size"] = float(min(fs, max_title_size))
			
			# 블록 간 최소 간격: 본문 폰트 기준으로 한 줄(line_height)의 절반~한 줄 정도 확보
			avg_font_size = base_font_size
			min_block_spacing = max(12, int(avg_font_size * 0.9))
			
			for sorted_idx, (original_idx, block) in enumerate(sorted_blocks):
				rendered_area = _render_block_text(
					block=block,
					draw=draw,
					img_original=img_original,
					korean_font_path=korean_font_path,
					rendered_areas=rendered_areas,
					min_block_spacing=min_block_spacing,
					page_index=page_index,
					block_index=original_idx,
					page_height=h,
					page_width=w,
				)
				if rendered_area is not None:
					rendered_areas.append(rendered_area)
			
			# Save final image with Korean text
			out_path = out_dir / f"page_{page_index+1:03d}.png"
			pil_img.save(str(out_path), "PNG")
			output_paths.append(out_path)
		else:
			# Fallback without OpenCV
			out_path = out_dir / f"page_{page_index+1:03d}.png"
			img_bytes = pix.tobytes("png")
			with open(out_path, "wb") as f:
				f.write(img_bytes)
			output_paths.append(out_path)
	
	doc.close()
	return output_paths


def render_inpainted_preview_images(pdf_path: Path, layout: dict, out_dir: Path, dpi: int = 180) -> List[Path]:
	"""
	Render each PDF page to a PNG image, remove text areas using OpenCV inpaint,
	and save to out_dir. Returns list of output file paths (one per page).
	If OpenCV is not available, renders plain images without inpaint.
	"""
	if fitz is None:
		raise RuntimeError("PyMuPDF(fitz)가 설치되어 있지 않습니다.")
	
	out_dir.mkdir(parents=True, exist_ok=True)
	doc = fitz.open(str(pdf_path))
	output_paths: List[Path] = []
	
	# scale factor from points (72dpi) to target dpi
	zoom = dpi / 72.0
	matrix = fitz.Matrix(zoom, zoom)
	
	for page_index, page in enumerate(doc):
		pix = page.get_pixmap(matrix=matrix, alpha=False)
		# Convert to numpy image (BGR)
		out_path = out_dir / f"page_{page_index+1:03d}.png"
		if _cv_available:
			# Convert PyMuPDF pixmap to numpy array directly
			img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))  # type: ignore
			# Convert RGB to BGR for OpenCV
			if pix.n == 3:
				img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # type: ignore
			elif pix.n == 4:
				img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)  # type: ignore
			h, w = img.shape[:2]
			# Build mask from layout blocks if present
			mask = np.zeros((h, w), dtype=np.uint8)  # type: ignore
			try:
				pages = layout.get("pages", [])
				if page_index < len(pages):
					page_layout = pages[page_index]
					lw = float(page_layout.get("width", w))
					lh = float(page_layout.get("height", h))
					sx = w / lw if lw else 1.0
					sy = h / lh if lh else 1.0
					for b in page_layout.get("blocks", []):
						x0, y0, x1, y1 = b.get("bbox", [0, 0, 0, 0])
						# Minimal padding to reduce blur area
						padding = 1
						rx0 = max(0, int(x0 * sx) - padding)
						ry0 = max(0, int(y0 * sy) - padding)
						rx1 = min(w - 1, int(x1 * sx) + padding)
						ry1 = min(h - 1, int(y1 * sy) + padding)
						cv2.rectangle(mask, (rx0, ry0), (rx1, ry1), color=255, thickness=-1)  # type: ignore
			except Exception:
				# ignore mask generation errors
				pass
			
			if mask.any():  # type: ignore
				# Calculate dynamic inpaint radius based on text block sizes
				# Average text block height to determine appropriate radius
				avg_height = 0
				block_count = 0
				try:
					pages = layout.get("pages", [])
					if page_index < len(pages):
						page_layout = pages[page_index]
						lw = float(page_layout.get("width", w))
						lh = float(page_layout.get("height", h))
						sy = h / lh if lh else 1.0
						for b in page_layout.get("blocks", []):
							x0, y0, x1, y1 = b.get("bbox", [0, 0, 0, 0])
							block_height = (y1 - y0) * sy
							if block_height > 0:
								avg_height += block_height
								block_count += 1
						if block_count > 0:
							avg_height = avg_height / block_count
				except Exception:
					pass
				
				# Minimal radius to reduce blur - use smallest possible value
				radius = 1
				
				# Use mask directly without dilation for minimal blur
				# TELEA method with minimal radius for least visible blur
				inpainted = cv2.inpaint(img, mask, radius, cv2.INPAINT_TELEA)  # type: ignore
				
				# Ensure text areas are completely removed by applying mask directly
				# This prevents any residual text from showing through
				mask_binary = (mask > 0).astype(np.uint8)  # type: ignore
				if len(img.shape) == 3:
					mask_3d = np.stack([mask_binary] * 3, axis=2)  # type: ignore
					# Only use inpainted pixels where mask exists, original elsewhere
					inpainted = np.where(mask_3d > 0, inpainted, img)  # type: ignore
			else:
				inpainted = img
			cv2.imwrite(str(out_path), inpainted)  # type: ignore
		else:
			# fallback - save raw pixmap as PNG
			img_bytes = pix.tobytes("png")
			with open(out_path, "wb") as f:
				f.write(img_bytes)
		output_paths.append(out_path)
	
	doc.close()
	return output_paths

def extract_layout_blocks_ocr(pdf_path: Path):
	"""
	Extract text blocks using OCR (Tesseract) for image-based PDFs.
	Uses industry-standard approach with proper line/paragraph grouping.
	
	Pipeline:
	1. Convert PDF to images (high DPI for better OCR)
	2. Run Tesseract OCR with word-level bounding boxes
	3. Group words into lines (Y-coordinate proximity)
	4. Group lines into paragraphs (Y-gap, indentation)
	5. Segment into columns (X-interval clustering)
	6. Sort in true reading order
	7. Suppress duplicates
	
	Returns same structure as extract_layout_blocks.
	Requires: pytesseract, pdf2image, Pillow, and tesseract binary installed.
	"""
	if pytesseract is None or convert_from_path is None:
		raise RuntimeError("OCR dependencies not installed. Install pytesseract, pdf2image, Pillow")
	
	# Convert PDF pages to images at higher DPI for better OCR
	try:
		images = convert_from_path(str(pdf_path), dpi=200)
	except Exception as e:
		raise RuntimeError(f"pdf2image conversion failed: {e}")
	
	pages = []
	
	for page_num, img in enumerate(images):
		width, height = img.size
		page_info = {"width": float(width), "height": float(height), "blocks": []}
		
		# Step 1: Run OCR with word-level bounding boxes
		try:
			ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang='eng')
		except Exception as e:
			print(f"OCR failed for page {page_num + 1}: {e}")
			pages.append(page_info)
			continue
		
		# Step 2: Extract words with confidence filtering
		words = []
		for i in range(len(ocr_data['text'])):
			text = ocr_data['text'][i].strip()
			if not text:
				continue
			
			conf = int(ocr_data['conf'][i])
			if conf < 40:  # Skip low-confidence text
				continue
			
			x = ocr_data['left'][i]
			y = ocr_data['top'][i]
			w = ocr_data['width'][i]
			h = ocr_data['height'][i]
			
			words.append({
				"text": text,
				"bbox": [x, y, x + w, y + h],
				"conf": conf
			})
		
		if not words:
			pages.append(page_info)
			continue
		
		# Step 3: Group words into lines (Y-coordinate proximity)
		# Sort words by Y coordinate first
		words.sort(key=lambda w: (w["bbox"][1], w["bbox"][0]))
		
		lines = []
		current_line = None
		
		for word in words:
			y0 = word["bbox"][1]
			y1 = word["bbox"][3]
			line_height = y1 - y0
			
			if current_line is None:
				current_line = {
					"words": [word],
					"bbox": word["bbox"][:],
					"line_height": line_height
				}
			else:
				prev_y0 = current_line["bbox"][1]
				prev_y1 = current_line["bbox"][3]
				prev_height = current_line["line_height"]
				
				# Check if word is on same line (Y overlap > 50%)
				overlap_y0 = max(prev_y0, y0)
				overlap_y1 = min(prev_y1, y1)
				overlap = max(0, overlap_y1 - overlap_y0)
				
				avg_height = (prev_height + line_height) / 2.0
				
				if overlap > avg_height * 0.5:
					# Same line - extend
					current_line["words"].append(word)
					current_line["bbox"][0] = min(current_line["bbox"][0], word["bbox"][0])
					current_line["bbox"][1] = min(current_line["bbox"][1], word["bbox"][1])
					current_line["bbox"][2] = max(current_line["bbox"][2], word["bbox"][2])
					current_line["bbox"][3] = max(current_line["bbox"][3], word["bbox"][3])
				else:
					# New line
					lines.append(current_line)
					current_line = {
						"words": [word],
						"bbox": word["bbox"][:],
						"line_height": line_height
					}
		
		if current_line is not None:
			lines.append(current_line)
		
		# Step 4: Convert lines to consistent format
		formatted_lines = []
		for line in lines:
			# Sort words in line by X coordinate (left to right)
			line["words"].sort(key=lambda w: w["bbox"][0])
			
			# Merge words into line text
			text_parts = []
			for i, word in enumerate(line["words"]):
				if i > 0:
					# Check horizontal gap to previous word
					prev_x1 = line["words"][i-1]["bbox"][2]
					curr_x0 = word["bbox"][0]
					gap = curr_x0 - prev_x1
					
					# Add space if gap is significant (> 5px)
					if gap > 5:
						text_parts.append(" ")
				
				text_parts.append(word["text"])
			
			line_text = "".join(text_parts).strip()
			
			if line_text:
				formatted_lines.append({
					"bbox": line["bbox"],
					"text": line_text,
					"font_size": line["line_height"],  # Use line height as proxy for font size
					"line_x0": line["bbox"][0]
				})
		
		# Step 5: Group lines into paragraphs
		paragraphs = _group_lines_into_paragraphs(formatted_lines, height)
		
		# Step 6: Convert paragraphs to blocks
		raw_blocks = []
		for para in paragraphs:
			text = _merge_paragraph_text(para)
			if not text.strip():
				continue
			
			raw_blocks.append({
				"bbox": para["bbox"],
				"text": text,
				"font_size": para["font_size"],
				"text_start_x": para["lines"][0]["line_x0"] if para["lines"] else para["bbox"][0],
				"is_bullet": para.get("is_bullet", False)
			})
		
		# Step 7: Segment into columns
		columns = _segment_columns(raw_blocks, width)
		
		# Step 8: Sort in true reading order
		ordered_blocks = []
		for column in columns:
			ordered_blocks.extend(column)
		
		# Step 9: Final duplicate suppression
		final_blocks = []
		for block in ordered_blocks:
			is_duplicate = False
			
			for existing in final_blocks:
				iou = _compute_iou(block["bbox"], existing["bbox"])
				text_sim = _text_similarity(block["text"], existing["text"])
				
				if iou > 0.8 or (iou > 0.5 and text_sim > 0.85):
					is_duplicate = True
					break
			
			if not is_duplicate:
				final_blocks.append({
					"bbox": block["bbox"],
					"text": block["text"],
					"font_size": block["font_size"],
					"text_start_x": block.get("text_start_x", block["bbox"][0])
				})
		
		page_info["blocks"] = final_blocks
		pages.append(page_info)
		
		num_cols = len(columns)
		print(f"Page {page_num + 1} (OCR): Extracted {len(words)} words → {len(formatted_lines)} lines → {len(paragraphs)} paragraphs → {len(final_blocks)} blocks in {num_cols} column(s)")
	
	return {"pages": pages}


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



def extract_layout_blocks(pdf_path: Path):
	"""
	Extract page sizes and text blocks (bbox + text + approx font size) using PyMuPDF.
	Extracts ALL visible text from PDF screen in reading order, including text in images/graphics.
	DO NOT use OCR - uses PyMuPDF's native text extraction with multiple methods for accuracy.
	
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
	
	for page_num, page in enumerate(doc):
		page_info = {"width": float(page.rect.width), "height": float(page.rect.height), "blocks": []}
		
		# Use multiple extraction methods to capture ALL visible text
		# Method 1: rawdict - preserves exact structure and position
		raw = page.get_text("rawdict")
		
		# Method 2: dict - alternative structure that might catch different text
		dict_text = page.get_text("dict")
		
		# Collect all text blocks with their positions
		all_blocks = []
		
		# Process rawdict blocks (primary method)
		for b in raw.get("blocks", []):
			if "lines" not in b:
				continue
			x0, y0, x1, y1 = None, None, None, None
			spans_sizes = []
			text_parts = []
			first_line_x0 = None
			
			for line_idx, line in enumerate(b.get("lines", [])):
				line_text_parts = []
				line_x0 = None
				for span in line.get("spans", []):
					t = span.get("text", "") or ""
					if t.strip():
						line_text_parts.append(t)
						spans_sizes.append(float(span.get("size", 0.0) or 0.0))
						sb = span.get("bbox", None)
						if sb and len(sb) == 4:
							sx0, sy0, sx1, sy1 = [float(v) for v in sb]
							if line_x0 is None:
								line_x0 = sx0
							else:
								line_x0 = min(line_x0, sx0)
							x0 = sx0 if x0 is None else min(x0, sx0)
							y0 = sy0 if y0 is None else min(y0, sy0)
							x1 = sx1 if x1 is None else max(x1, sx1)
							y1 = sy1 if y1 is None else max(y1, sy1)
				
				if line_text_parts:
					# Keep line breaks inside the block
					text_parts.append(" ".join(line_text_parts))
					if first_line_x0 is None and line_x0 is not None:
						first_line_x0 = line_x0
			
			block_text = "\n".join(text_parts).strip()
			if not block_text:
				continue
			if x0 is None or y0 is None or x1 is None or y1 is None:
				continue
			
			# Calculate representative font size
			font_size = 0.0
			if spans_sizes:
				sorted_sizes = sorted(spans_sizes)
				mid = len(sorted_sizes) // 2
				if len(sorted_sizes) % 2 == 0:
					font_size = (sorted_sizes[mid - 1] + sorted_sizes[mid]) / 2.0
				else:
					font_size = sorted_sizes[mid]
			
			all_blocks.append({
				"bbox": [float(x0), float(y0), float(x1), float(y1)],
				"text": block_text,
				"font_size": float(font_size),
				"text_start_x": float(first_line_x0) if first_line_x0 is not None else float(x0),
				"source": "rawdict"
			})
		
		# Also check dict blocks for any additional text (e.g., in images/graphics)
		# This helps catch text that might be embedded in images
		if dict_text and "blocks" in dict_text:
			for b in dict_text.get("blocks", []):
				if b.get("type") == 0:  # Text block
					bbox = b.get("bbox", [])
					if len(bbox) == 4 and b.get("lines"):
						text_lines = []
						for line in b.get("lines", []):
							line_text = " ".join([span.get("text", "") for span in line.get("spans", []) if span.get("text", "").strip()])
							if line_text.strip():
								text_lines.append(line_text.strip())
						
						if text_lines:
							block_text = "\n".join(text_lines)
							x0, y0, x1, y1 = bbox
							
							# Check if this block overlaps with existing blocks
							# If it's significantly different, add it
							is_duplicate = False
							for existing in all_blocks:
								ex0, ey0, ex1, ey1 = existing["bbox"]
								# Check overlap
								overlap_x = max(0, min(ex1, x1) - max(ex0, x0))
								overlap_y = max(0, min(ey1, y1) - max(ey0, y0))
								overlap_area = overlap_x * overlap_y
								existing_area = (ex1 - ex0) * (ey1 - ey0)
								new_area = (x1 - x0) * (y1 - y0)
								
								# If significant overlap (>80%) and similar text, skip
								if overlap_area > 0.8 * min(existing_area, new_area):
									# Check text similarity
									if block_text.strip().lower() in existing["text"].strip().lower() or existing["text"].strip().lower() in block_text.strip().lower():
										is_duplicate = True
										break
							
							if not is_duplicate:
								# Get font size from spans
								font_size = 12.0  # default
								for line in b.get("lines", []):
									for span in line.get("spans", []):
										if "size" in span:
											font_size = float(span["size"])
											break
									if font_size != 12.0:
										break
								
								all_blocks.append({
									"bbox": [float(x0), float(y0), float(x1), float(y1)],
									"text": block_text,
									"font_size": float(font_size),
									"text_start_x": float(x0),
									"source": "dict"
								})
		
		# Sort blocks by reading order: top to bottom, then left to right
		# This ensures we capture text in the exact order it appears on screen
		all_blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))  # Sort by y, then x
		
		# Remove duplicates and merge very close blocks
		filtered_blocks = []
		for block in all_blocks:
			# Check if this block is too close to previous blocks (likely duplicate)
			is_duplicate = False
			for existing in filtered_blocks:
				ex0, ey0, ex1, ey1 = existing["bbox"]
				bx0, by0, bx1, by1 = block["bbox"]
				
				# Check if blocks are very close vertically and horizontally
				vertical_distance = abs((ey0 + ey1) / 2 - (by0 + by1) / 2)
				horizontal_distance = abs((ex0 + ex1) / 2 - (bx0 + bx1) / 2)
				
				# If blocks are very close and text is similar, skip
				if vertical_distance < 5 and horizontal_distance < 50:
					existing_text = existing["text"].strip().lower()
					new_text = block["text"].strip().lower()
					if existing_text == new_text or existing_text in new_text or new_text in existing_text:
						is_duplicate = True
						break
			
			if not is_duplicate:
				# Clean up the block data for output
				block_data = {
					"bbox": block["bbox"],
					"text": block["text"],
					"font_size": block["font_size"],
					"text_start_x": block["text_start_x"]
				}
				filtered_blocks.append(block_data)
		
		page_info["blocks"] = filtered_blocks
		pages.append(page_info)
		
		print(f"Page {page_num + 1}: Extracted {len(filtered_blocks)} text blocks (total {len(all_blocks)} before filtering)")
	
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


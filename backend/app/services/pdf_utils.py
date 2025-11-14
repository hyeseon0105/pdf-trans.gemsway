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
			first_line_x0 = None  # Track first line's starting x position for alignment
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
					# keep line breaks inside the block
					text_parts.append("".join(line_text_parts))
					# Store first line's x0 for alignment
					if first_line_x0 is None and line_x0 is not None:
						first_line_x0 = line_x0
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
			block_data = {
				"bbox": [float(x0), float(y0), float(x1), float(y1)],
				"text": block_text,
				"font_size": float(font_size),
			}
			# Store first line's x0 for text alignment (if available)
			if first_line_x0 is not None:
				block_data["text_start_x"] = float(first_line_x0)
			page_info["blocks"].append(block_data)
		pages.append(page_info)
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
						
						# Skip image region detection in backend - render all text blocks
						# Frontend will handle image region detection for display
						# Check if this text block is on an image region (DISABLED for now)
						# if _is_image_region(img, rx0, ry0, rx1, ry1):
						# 	image_blocks_skipped += 1
						# 	continue
						
						# Add to mask for inpaint
						padding = 3
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
			
			# Apply inpaint to remove original text
			if mask.any():  # type: ignore
				kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # type: ignore
				mask_dilated = cv2.dilate(mask, kernel, iterations=2)  # type: ignore
				radius = 5
				img = cv2.inpaint(img, mask_dilated, radius, cv2.INPAINT_NS)  # type: ignore
			
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
			rendered_areas: List[tuple[float, float, float, float]] = []  # List of (x0, y0, x1, y1) for rendered text
			# Calculate average font size for spacing calculation
			avg_font_size = 12  # Default
			if text_blocks:
				font_sizes = [int(b.get("font_size", 12)) for b in text_blocks]
				if font_sizes:
					avg_font_size = sum(font_sizes) / len(font_sizes)
			min_block_spacing = max(10, int(avg_font_size * 0.3))  # Minimum spacing between blocks (pixels), proportional to font size
			
			for sorted_idx, (original_idx, block) in enumerate(sorted_blocks):
				x0, y0, x1, y1 = block["bbox"]
				text = block["text"]
				font_size = int(block["font_size"])
				block_width = x1 - x0
				block_height = y1 - y0
				# Get original text start position if available (for alignment)
				text_start_x = block.get("text_start_x", x0)
				
				if text.strip():
					# Load font at appropriate size
					try:
						if korean_font_path and korean_font_path.endswith('.ttc'):
							font = ImageFont.truetype(korean_font_path, font_size)
						elif korean_font_path and korean_font_path.endswith('.ttf'):
							font = ImageFont.truetype(korean_font_path, font_size)
						else:
							font = ImageFont.load_default()
							print(f"Warning: Using default font for block {original_idx} (Korean font not found)")
					except Exception as e:
						font = ImageFont.load_default()
						print(f"Warning: Failed to load font for block {original_idx}: {e}")
					
					# Detect original text color from original image (before inpaint)
					text_color = _detect_text_color(img_original, x0, y0, x1, y1)
					
					# Use appropriate margin to prevent text from touching edges
					# Margin helps prevent text overlap and improves readability
					text_margin = max(2, int(font_size * 0.15))  # Margin proportional to font size, minimum 2px
					# Use 90% of block width to ensure proper margins on both sides
					available_width = max(int(block_width * 0.90), block_width - text_margin * 2, font_size)
					lines = _wrap_text(text, font, available_width)
					
					# Calculate line height - consistent spacing based on font size
					# Increase line height significantly to prevent text overlap (especially for Korean with descenders/ascenders)
					try:
						bbox = font.getbbox("한글")
						base_line_height = bbox[3] - bbox[1]
						# Line height should be proportional to font size for consistency
						# Use 2.2x spacing to prevent descenders from overlapping with next line's ascenders
						# Increased to 2.2x for much better spacing and readability
						line_height = base_line_height * 2.2  # 120% spacing to prevent overlap
					except:
						# Fallback if getbbox fails
						line_height = font_size * 2.2  # 120% spacing to prevent overlap
					
					# Calculate total text height needed
					total_lines = len(lines)
					total_text_height = total_lines * line_height
					available_height = block_height - (text_margin * 2)
					
					# If text doesn't fit, reduce font size until it fits
					# Keep adjusting until ALL text fits
					adjusted_font_size = font_size
					adjusted_font = font
					adjusted_line_height = line_height
					max_iterations = 5
					iteration = 0
					
					while iteration < max_iterations:
						total_text_height = total_lines * adjusted_line_height
						
						if total_text_height <= available_height:
							# Text fits, we're done
							break
						
						# Calculate scale factor to fit all text
						scale_factor = available_height / total_text_height
						# Keep minimum font size reasonable (10px) and preserve original size better
						min_font_size = max(10, int(font_size * 0.5))  # At least 10px, or 50% of original
						adjusted_font_size = max(int(adjusted_font_size * scale_factor * 0.95), min_font_size)  # 5% margin
						
						# Reload font with adjusted size
						try:
							if korean_font_path and korean_font_path.endswith('.ttc'):
								adjusted_font = ImageFont.truetype(korean_font_path, adjusted_font_size)
							elif korean_font_path and korean_font_path.endswith('.ttf'):
								adjusted_font = ImageFont.truetype(korean_font_path, adjusted_font_size)
							else:
								adjusted_font = ImageFont.load_default()
							
							# Recalculate line height with new font - keep consistent ratio
							try:
								bbox = adjusted_font.getbbox("한글")
								base_line_height = bbox[3] - bbox[1]
								adjusted_line_height = base_line_height * 2.2  # 120% spacing to prevent overlap
							except:
								adjusted_line_height = adjusted_font_size * 2.2  # 120% spacing to prevent overlap
							
							# Re-wrap text with adjusted font
							lines = _wrap_text(text, adjusted_font, available_width)
							total_lines = len(lines)
							
							iteration += 1
						except Exception as e:
							print(f"Warning: Failed to adjust font size: {e}")
							break
					
					# Check for overlaps with previously rendered blocks
					# Adjust y0 if this block overlaps with previous blocks
					actual_y0 = y0
					actual_y1 = y1
					
					# Calculate estimated text height
					estimated_text_height = total_lines * adjusted_line_height
					estimated_y1 = actual_y0 + text_margin + estimated_text_height + text_margin
					
					# Check overlap with previous rendered areas - more aggressive detection
					for prev_x0, prev_y0, prev_x1, prev_y1 in rendered_areas:
						# Check if blocks overlap horizontally (with some tolerance)
						horizontal_overlap = not (x1 < prev_x0 - 5 or x0 > prev_x1 + 5)  # 5px tolerance
						if horizontal_overlap:
							# Check if this block starts too close to previous block's end
							# Use larger spacing to prevent any overlap
							required_spacing = max(min_block_spacing, adjusted_font_size * 0.5)  # At least 50% of font size
							if actual_y0 < prev_y1 + required_spacing:
								# Adjust y0 to add spacing
								actual_y0 = prev_y1 + required_spacing
								# Recalculate available height
								available_height = (y1 - actual_y0) - (text_margin * 2)
								# If available height is too small, reduce font size further
								if available_height < estimated_text_height:
									# Reduce font size to fit
									scale_factor = available_height / estimated_text_height if estimated_text_height > 0 else 1.0
									adjusted_font_size = max(int(adjusted_font_size * scale_factor * 0.9), max(10, int(font_size * 0.5)))
									try:
										if korean_font_path and korean_font_path.endswith('.ttc'):
											adjusted_font = ImageFont.truetype(korean_font_path, adjusted_font_size)
										elif korean_font_path and korean_font_path.endswith('.ttf'):
											adjusted_font = ImageFont.truetype(korean_font_path, adjusted_font_size)
										else:
											adjusted_font = ImageFont.load_default()
										# Recalculate line height
										try:
											bbox = adjusted_font.getbbox("한글")
											base_line_height = bbox[3] - bbox[1]
											adjusted_line_height = base_line_height * 2.2  # 120% spacing to prevent overlap
										except:
											adjusted_line_height = adjusted_font_size * 2.2  # 120% spacing to prevent overlap
										# Re-wrap text
										lines = _wrap_text(text, adjusted_font, available_width)
										total_lines = len(lines)
										estimated_text_height = total_lines * adjusted_line_height
									except Exception as e:
										print(f"Warning: Failed to adjust font for overlap: {e}")
					
					# Draw each line - ensure ALL lines are rendered
					current_y = actual_y0 + text_margin
					rendered_lines = 0
					first_line_y = current_y
					last_line_y = current_y
					
					for line_idx, line in enumerate(lines):
						# Ensure we have space - if not, reduce line height slightly but still render
						# Add extra spacing between lines to prevent overlap
						min_line_height = adjusted_font_size * 1.5  # Minimum line height (50% spacing) - increased to prevent overlap
						if current_y + adjusted_line_height > y1 - text_margin:
							# Use smaller line height to fit, but still render the line
							actual_line_height = min(adjusted_line_height, y1 - text_margin - current_y)
							# Ensure minimum line height to prevent overlap
							if actual_line_height < min_line_height:
								# Use minimum line height to prevent text overlap
								actual_line_height = max(min_line_height, adjusted_font_size * 1.3)  # At least 30% spacing
						else:
							actual_line_height = adjusted_line_height
						
						# Calculate text width for this line
						try:
							line_bbox = adjusted_font.getbbox(line)
							line_width = line_bbox[2] - line_bbox[0]
						except:
							# Fallback: estimate width
							line_width = len(line) * adjusted_font_size * 0.6
						
						# Use original text start position to match alignment
						# Calculate offset from bbox left edge
						text_start_offset = text_start_x - x0
						# Apply same offset to maintain original alignment
						text_x = x0 + text_start_offset + text_margin
						
						# Ensure text doesn't go outside block boundaries
						if text_x + line_width > x1 - text_margin:
							# If text is too wide, ensure it doesn't overflow
							text_x = max(x0 + text_margin, x1 - line_width - text_margin)
						
						draw.text((int(text_x), current_y), line, fill=text_color, font=adjusted_font)
						last_line_y = current_y + actual_line_height
						current_y += actual_line_height
						rendered_lines += 1
					
					if rendered_lines > 0:
						# Record the actual rendered area for overlap detection
						# Use actual rendered bounds with extra padding
						rendered_text_x0 = min(x0, text_x) - 2  # Small padding
						rendered_text_x1 = max(x1, text_x + line_width) + 2  # Small padding
						rendered_text_y0 = first_line_y - 2  # Small padding above
						# Add extra spacing below to prevent next block from overlapping
						extra_spacing = max(min_block_spacing, adjusted_font_size * 0.3)
						rendered_text_y1 = last_line_y + extra_spacing  # Add spacing for next block
						rendered_areas.append((rendered_text_x0, rendered_text_y0, rendered_text_x1, rendered_text_y1))
						
						if rendered_lines < total_lines:
							print(f"WARNING: Block {original_idx}: Only rendered {rendered_lines}/{total_lines} lines! Missing {total_lines - rendered_lines} lines. Text: '{text[:100]}...'")
							print(f"  Block size: {block_width}x{block_height}, Font: {adjusted_font_size}px, Available height: {available_height}px")
						else:
							print(f"Block {original_idx}: Successfully rendered all {rendered_lines}/{total_lines} lines, font_size={adjusted_font_size}, y_adjust={actual_y0 - y0:.1f}px")
					else:
						print(f"ERROR: Block {original_idx}: No lines rendered for text: '{text[:100]}...'")
						print(f"  Block size: {block_width}x{block_height}, Font: {font_size}px, Available height: {available_height}px")
			
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
						# Slightly larger padding for better edge handling
						padding = 3
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
				
				# Dynamic radius: based on average text height, but capped between 2-8
				# For larger text, use larger radius for smoother blending
				if avg_height > 0:
					radius = max(2, min(8, int(avg_height * 0.15)))
				else:
					radius = 5  # default
				
				# Dilate mask more aggressively to ensure text is completely removed
				# Use a larger kernel and more iterations to cover text edges
				kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # type: ignore
				mask_dilated = cv2.dilate(mask, kernel, iterations=2)  # type: ignore
				
				# NS method works better for textured/colored backgrounds
				# It uses Navier-Stokes equations for more natural inpainting
				# Use larger radius for better text removal
				inpainted = cv2.inpaint(img, mask_dilated, max(radius, 5), cv2.INPAINT_NS)  # type: ignore
				
				# Ensure text areas are completely removed by applying mask directly
				# This prevents any residual text from showing through
				mask_binary = (mask_dilated > 0).astype(np.uint8)  # type: ignore
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


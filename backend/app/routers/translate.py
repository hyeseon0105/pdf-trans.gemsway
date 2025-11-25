import re
import uuid
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from ..config import UPLOADS_DIR, TRANSLATED_DIR, PREVIEWS_DIR
from ..services.pdf_utils import (
	extract_text_from_pdf,
	create_pdf_from_text,
	extract_layout_blocks,
	extract_layout_blocks_ocr,
	render_inpainted_preview_images,
	render_high_quality_preview_images,
)
from ..services.translate_service import translate_text
from ..services.translation_review import review_translation

router = APIRouter()


@router.post("/translate/pdf")
async def translate_pdf(file: UploadFile = File(...)):
	if file.content_type != "application/pdf":
		raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

	# Save upload
	upload_id = str(uuid.uuid4())
	upload_path = UPLOADS_DIR / f"{upload_id}.pdf"
	with open(upload_path, "wb") as f:
		f.write(await file.read())

	# 1단계: 기본 텍스트 추출 시도 (텍스트 레이어가 있는 PDF)
	try:
		text = extract_text_from_pdf(upload_path)
	except Exception as e:
		raise HTTPException(status_code=400, detail=f"PDF 텍스트 추출 실패: {e}")

	layout = None

	# 2단계: PyMuPDF 기반 레이아웃 추출 우선 사용
	# (텍스트 레이어가 있는 일반 PDF)
	if text.strip():
		try:
			layout = extract_layout_blocks(upload_path)
			total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))
			# Count non-empty text blocks
			non_empty_blocks = sum(
				len([b for b in p.get("blocks", []) if (b.get("text", "") or "").strip()])
				for p in layout.get("pages", [])
			)
			
			print(f"Extracted {total_blocks} total blocks ({non_empty_blocks} non-empty) from PDF using PyMuPDF native extraction")
			
			if total_blocks == 0:
				# 레이아웃 블록이 전혀 없으면 OCR로 재시도
				layout = None
		except Exception as e:
			print(f"Error extracting layout blocks (native): {e}")
			import traceback
			traceback.print_exc()
			layout = None

	# 3단계: 텍스트 레이어가 없거나, 레이아웃 블록이 없는 경우 → OCR 기반 추출로 폴백
	if not text.strip() or layout is None:
		print("No extractable text or layout from native method, falling back to OCR-based extraction.")
		try:
			layout = extract_layout_blocks_ocr(upload_path)
			# OCR 레이아웃에서 전체 텍스트를 다시 구성
			pages = layout.get("pages", [])
			blocks_text: list[str] = []
			for p in pages:
				for b in p.get("blocks", []):
					t = (b.get("text", "") or "").strip()
					if t:
						blocks_text.append(t)
			text = "\n\n".join(blocks_text)

			if not text.strip():
				raise HTTPException(status_code=400, detail="PDF에서 추출 가능한 텍스트가 없습니다. (이미지 기반 PDF)")

			total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))
			print(f"Extracted {total_blocks} blocks from PDF using OCR-based extraction")
		except HTTPException:
			# 위에서 이미 의미 있는 메시지로 래이즈 한 경우 그대로 전달
			raise
		except Exception as e:
			print(f"Error extracting layout blocks with OCR: {e}")
			import traceback
			traceback.print_exc()
			raise HTTPException(status_code=500, detail=f"OCR 기반 PDF 텍스트 추출 실패: {e}")

	# Translate each block individually in order to maintain 1:1 mapping
	# This ensures accurate translation matching and preserves original structure
	try:
		def _normalize(value: str) -> str:
			return " ".join((value or "").split())

		total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))
		# DO NOT use translation cache - translate fresh from original PDF only
		translated_blocks_text: list[str] = []  # Collect all translated text for full text output
		translated_blocks_by_position: list[str] = []  # Track translations by position for context

		if total_blocks > 0:
			# Translate each block fresh from original PDF, maintaining exact structure
			# This ensures 1:1 mapping and preserves original paragraph order, line breaks, and item structure
			for page_idx, page in enumerate(layout.get("pages", [])):
				blocks = page.get("blocks", [])
				
				for block_idx, block in enumerate(blocks):
					original_text = (block.get("text", "") or "").strip()
					if not original_text:
						block["translated_text"] = ""
						translated_blocks_by_position.append("")
						continue

					normalized_text = _normalize(original_text)
					if not normalized_text:
						block["translated_text"] = ""
						translated_blocks_by_position.append("")
						continue

					# DO NOT use cache - always translate fresh from original

					# Build context from previously translated blocks (for this page only)
					# Use already-translated blocks from current page for context
					prev_translated_context = ""
					if block_idx > 0 and len(translated_blocks_by_position) > 0:
						# Get the last 1-2 translated blocks for context
						prev_contexts = []
						for i in range(max(0, block_idx - 2), block_idx):
							if i < len(translated_blocks_by_position) and translated_blocks_by_position[i]:
								prev_contexts.append(translated_blocks_by_position[i])
						if prev_contexts:
							prev_translated_context = " ".join(prev_contexts[-2:])  # Use last 2
					
					# Get next original blocks for context
					next_original_context = ""
					if block_idx < len(blocks) - 1:
						next_texts = []
						for i in range(block_idx + 1, min(len(blocks), block_idx + 3)):
							next_text = (blocks[i].get("text", "") or "").strip()
							if next_text:
								next_texts.append(next_text)
						if next_texts:
							next_original_context = " ".join(next_texts[:2])  # Use first 2
					
					# Build translation prompt with natural Korean emphasis
					# Always translate fresh - no cache
					translation_instructions = (
						"다음 영어 텍스트를 자연스러운 한국어로 번역해주세요.\n\n"
						"번역 원칙:\n"
						"1. 【직역 금지】 의미를 정확히 전달하는 자연스러운 한국어로 의역\n"
						"2. 【자연스러운 어순】 한국어 어순에 맞게 문장 구조 재배치\n"
						"3. 【읽기 쉽게】 전문 용어도 이해하기 쉽게 번역\n"
						"4. 【문맥 고려】 문맥에 맞는 적절한 한국어 표현 사용\n"
						"5. 【구조 유지】 문단, 줄바꿈, 리스트 구조는 원본과 동일하게\n"
						"6. 【완전성】 모든 내용 번역, 추가 내용 없음\n"
						"7. 【자연스러운 종결】 제목은 체언형, 본문은 '~합니다/됩니다/있습니다' 등 자연스러운 종결어미 사용\n\n"
					)
					
					# Build context-aware prompt
					if prev_translated_context or next_original_context:
						context_parts = []
						if prev_translated_context and len(prev_translated_context) < 500:
							context_parts.append(f"[이전 문맥 - 이미 번역됨]: {prev_translated_context}")
						context_parts.append(f"[번역할 텍스트]: {original_text}")
						if next_original_context and len(next_original_context) < 500:
							context_parts.append(f"[다음 문맥 - 원문]: {next_original_context}")
						
						translation_prompt = translation_instructions + "\n\n".join(context_parts)
						
						# Limit prompt size
						if len(translation_prompt) > 2500:
							# Simplify to immediate neighbors only
							context_parts = []
							if prev_translated_context:
								context_parts.append(f"[이전]: {prev_translated_context[:200]}")
							context_parts.append(f"[번역]: {original_text}")
							if next_original_context:
								context_parts.append(f"[다음]: {next_original_context[:200]}")
							translation_prompt = translation_instructions + "\n\n".join(context_parts)
					else:
						translation_prompt = translation_instructions + f"[번역할 텍스트]: {original_text}"
					
					# Translate fresh from original (no cache)
					try:
						print(f"Page {page_idx + 1}, Block {block_idx + 1}: Translating fresh from original ({len(original_text)} chars): '{original_text[:80]}...'")
						translated_block = translate_text(translation_prompt, target_lang="ko")
						
						# Extract the translation of the current block
						# Remove instruction text and context markers if present
						markers_to_remove = [
							"[번역할 텍스트]:", "[번역]:", "[이전 문맥", "[다음 문맥", "[이전]:", "[다음]:",
							"Text to translate:", "Translate:", "Previous", "Following"
						]
						
						# Check if any markers are present
						has_markers = any(marker in translated_block for marker in markers_to_remove)
						
						if has_markers:
							# Try to extract the main translation part
							if "[이전" in translated_block and "[다음" in translated_block:
								# Extract middle part between markers
								parts = translated_block.split("[다음")
								if parts:
									middle = parts[0].split("[이전")[-1]
									translated_block = middle.strip()
							elif "[이전" in translated_block:
								parts = translated_block.split("[이전", 1)
								if len(parts) > 1:
									# Get everything after the marker
									after_marker = parts[1]
									# Remove the marker line (up to first newline or colon)
									if "]:" in after_marker:
										translated_block = after_marker.split("]:", 1)[-1].strip()
									elif "\n" in after_marker:
										translated_block = after_marker.split("\n", 1)[-1].strip()
									else:
										translated_block = after_marker.strip()
							elif "[다음" in translated_block:
								parts = translated_block.split("[다음", 1)
								if parts:
									translated_block = parts[0].strip()
							
							# Remove any remaining instruction markers using regex
							translated_block = re.sub(r'\[번역할 텍스트\]:?\s*', '', translated_block)
							translated_block = re.sub(r'\[번역\]:?\s*', '', translated_block)
							translated_block = re.sub(r'\[이전[^\]]*\]:?[^\n]*\n?', '', translated_block)
							translated_block = re.sub(r'\[다음[^\]]*\]:?[^\n]*\n?', '', translated_block)
							translated_block = re.sub(r'^(Text to translate|Translate|Previous|Following)( context)?:\s*', '', translated_block, flags=re.IGNORECASE | re.MULTILINE)
							translated_block = translated_block.strip()
						
						# Validate translation
						if not translated_block or not translated_block.strip():
							print(f"Warning: Translation returned empty for block, retrying without context")
							# Retry without context
							simple_prompt = translation_instructions + f"[번역할 텍스트]: {original_text}"
							translated_block = translate_text(simple_prompt, target_lang="ko")
							# Clean up markers
							translated_block = re.sub(r'\[번역할 텍스트\]:?\s*', '', translated_block)
							translated_block = re.sub(r'^(Text to translate|번역할 텍스트):?\s*', '', translated_block, flags=re.IGNORECASE)
							translated_block = translated_block.strip()
						
						if not translated_block or not translated_block.strip():
							print(f"Warning: Translation still empty, will retry translation")
							# 원본 텍스트를 사용하지 않고 다시 번역 시도
							try:
								translated_block = translate_text(original_text, target_lang="ko")
								if not translated_block or not translated_block.strip():
									print(f"Error: Translation failed completely for block")
									continue  # 이 블록은 건너뜀
							except Exception as retry_e:
								print(f"Error: Retry translation failed: {retry_e}")
								continue  # 이 블록은 건너뜀
						
						# Store translation (but don't use as cache for future blocks)
						block["translated_text"] = translated_block
						translated_blocks_text.append(translated_block)
						translated_blocks_by_position.append(translated_block)
						
						print(f"Page {page_idx + 1}, Block {block_idx + 1}: Translated: '{original_text[:50]}...' -> '{translated_block[:50]}...'")
					except Exception as e:
						print(f"Error translating block: {e}")
						import traceback
						traceback.print_exc()
						# Fallback: translate without context
						try:
							simple_prompt = translation_instructions + f"[번역할 텍스트]: {original_text}"
							translated_block = translate_text(simple_prompt, target_lang="ko")
							# Clean up markers
							translated_block = re.sub(r'\[번역할 텍스트\]:?\s*', '', translated_block)
							translated_block = re.sub(r'^(Text to translate|번역할 텍스트):?\s*', '', translated_block, flags=re.IGNORECASE)
							translated_block = translated_block.strip()
							if not translated_block or not translated_block.strip():
								print(f"Error: Translation failed for block, skipping")
								continue  # 이 블록은 건너뜀
						except Exception as retry_e2:
							print(f"Error: Final retry translation failed: {retry_e2}")
							continue  # 이 블록은 건너뜀
						
						block["translated_text"] = translated_block
						translated_blocks_text.append(translated_block)
						translated_blocks_by_position.append(translated_block)

			# Create full translated text from blocks (for compatibility with existing code)
			translated = "\n\n".join(translated_blocks_text)
		else:
			# No blocks -> translate full text and create synthetic blocks
			try:
				translated = translate_text(text, target_lang="ko")
			except Exception as e:
				raise HTTPException(status_code=500, detail=f"번역 실패: {e}")
			
			translated_paragraphs = [p.strip() for p in translated.split("\n\n") if p.strip()]
			num_pages = len(layout.get("pages", []))
			if num_pages > 0:
				paras_per_page = max(1, len(translated_paragraphs) // num_pages)
				for idx, page in enumerate(layout.get("pages", [])):
					start = idx * paras_per_page
					end = start + paras_per_page if idx < num_pages - 1 else len(translated_paragraphs)
					page_paras = translated_paragraphs[start:end]

					page_width = page.get("width", 595.0)
					page_height = page.get("height", 842.0)
					margin = 40
					block_height = 60
					y_pos = margin

					page["blocks"] = []
					for para in page_paras:
						if y_pos + block_height > page_height - margin:
							break
						page["blocks"].append(
							{
								"bbox": [margin, y_pos, page_width - margin, y_pos + block_height],
								"text": "",
								"translated_text": para,
								"font_size": 12,
							}
						)
						y_pos += block_height + 10
	except Exception as e:
		print(f"Error in block translation: {e}")
		import traceback
		traceback.print_exc()
		# Fallback: translate full text
		try:
			translated = translate_text(text, target_lang="ko")
		except Exception as e2:
			raise HTTPException(status_code=500, detail=f"번역 실패: {e2}")

	# 페이지별 영어/한국어 텍스트를 평탄화해서 디버깅/검수에 활용
	def _build_page_texts(layout_data: dict) -> dict:
		pages = layout_data.get("pages", [])
		pages_en: list[list[str]] = []
		pages_ko: list[list[str]] = []
		
		for page in pages:
			blocks = page.get("blocks", [])
			# bbox 기준으로 읽기 순서 정렬 (y, x)
			sorted_blocks = sorted(
				blocks,
				key=lambda b: (
					(b.get("bbox") or [0, 0, 0, 0])[1],
					(b.get("bbox") or [0, 0, 0, 0])[0],
				),
			)
			en_lines: list[str] = []
			ko_lines: list[str] = []
			for b in sorted_blocks:
				orig = (b.get("text", "") or "").strip()
				tran = (b.get("translated_text", "") or "").strip()
				if orig:
					en_lines.append(orig)
				# 번역이 없으면 원문을 그대로 남겨서 누락을 쉽게 발견할 수 있게 함
				if tran:
					ko_lines.append(tran)
				elif orig:
					ko_lines.append(f"[MISSING TRANSLATION] {orig}")
			pages_en.append(en_lines)
			pages_ko.append(ko_lines)
		
		return {"english": pages_en, "korean": pages_ko}

	page_texts = _build_page_texts(layout)

	# Build high-quality preview images with Korean text rendered
	# This must be done AFTER translation so that translated_text is available in layout
	preview_info = None
	try:
		preview_id = str(uuid.uuid4())
		out_dir = PREVIEWS_DIR / preview_id
		text_overlay_dir = PREVIEWS_DIR / f"{preview_id}_text"
		render_high_quality_preview_images(upload_path, layout, out_dir, text_overlay_dir, dpi=300, upscale_factor=1.5)
		preview_count = len(list(out_dir.glob("*.png")))
		if preview_count > 0:
			preview_info = {"id": preview_id, "count": preview_count}
		else:
			print(f"Warning: No preview images generated for {preview_id}")
	except Exception as e:
		print(f"Error generating high-quality preview images: {e}")
		import traceback
		traceback.print_exc()
		# Fallback to old method
		try:
			preview_id = str(uuid.uuid4())
			out_dir = PREVIEWS_DIR / preview_id
			render_inpainted_preview_images(upload_path, layout, out_dir)
			preview_count = len(list(out_dir.glob("*.png")))
			if preview_count > 0:
				preview_info = {"id": preview_id, "count": preview_count}
		except Exception as e2:
			print(f"Error with fallback preview generation: {e2}")
			preview_info = None

	# Generate translated PDF (simple text PDF for download fallback)
	file_id = str(uuid.uuid4())
	output_path = TRANSLATED_DIR / f"{file_id}.pdf"
	try:
		create_pdf_from_text(translated, output_path)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 PDF 생성 실패: {e}")

	# 자동 번역 검수 수행
	review_result = None
	try:
		review_result = review_translation(text, translated)
	except Exception as e:
		# 검수 실패해도 번역 결과는 반환
		pass

	return {
		"upload_id": upload_id,
		"file_id": file_id,
		"original_text": text,  # 원문 텍스트 추가
		"translated_text": translated,
		"layout": layout,
		"preview": preview_info,
		"review": review_result,  # 검수 결과 추가
	}


@router.get("/download/{file_id}")
def download_pdf(file_id: str):
	path = TRANSLATED_DIR / f"{file_id}.pdf"
	if not path.exists():
		print(f"[PDF 다운로드] 파일 없음: {file_id}")
		raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
	
	file_size = path.stat().st_size
	print(f"[PDF 다운로드] 시작: file_id={file_id}, 크기={file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")
	
	try:
		# 큰 파일을 위한 스트리밍 응답
		return FileResponse(
			path, 
			filename="translated.pdf", 
			media_type="application/pdf",
			headers={
				"Content-Length": str(file_size),
				"Content-Disposition": f'attachment; filename="translated.pdf"'
			}
		)
	except Exception as e:
		print(f"[PDF 다운로드] 오류: {e}")
		import traceback
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"파일 다운로드 중 오류 발생: {e}")


@router.get("/uploads/{upload_id}")
def get_uploaded_pdf(upload_id: str):
	path = UPLOADS_DIR / f"{upload_id}.pdf"
	if not path.exists():
		raise HTTPException(status_code=404, detail="업로드 파일을 찾을 수 없습니다.")
	return FileResponse(path, filename="original.pdf", media_type="application/pdf")


class ReviewRequest(BaseModel):
	original_pdf_path: Optional[str] = None
	translated_text: Optional[str] = None


@router.post("/review/translation")
async def review_translation_endpoint(request: ReviewRequest):
	"""
	번역 검수 및 보정 엔드포인트
	
	Request Body:
		{
			"original_pdf_path": "C:\\Users\\HP\\OneDrive\\바탕 화면\\젬스웨이\\Brochure-Summit-System-190272-937-REV10_251031.pdf",
			"translated_text": "번역된 텍스트..." (선택사항)
		}
	
	Returns:
		JSON 형식의 검수 결과
	"""
	try:
		# 원문 추출
		if request.original_pdf_path:
			original_path = Path(request.original_pdf_path)
			if not original_path.exists():
				raise HTTPException(status_code=404, detail=f"원문 PDF 파일을 찾을 수 없습니다: {request.original_pdf_path}")
			original_text = extract_text_from_pdf(original_path)
		else:
			raise HTTPException(status_code=400, detail="original_pdf_path가 필요합니다.")
		
		if not original_text.strip():
			raise HTTPException(status_code=400, detail="원문 PDF에서 텍스트를 추출할 수 없습니다.")
		
		# 번역문이 없으면 번역 수행
		if not request.translated_text:
			translated_text = translate_text(original_text, target_lang="ko")
		else:
			translated_text = request.translated_text
		
		# 검수 수행
		review_result = review_translation(original_text, translated_text)
		
		return review_result
		
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 검수 중 오류 발생: {str(e)}")


@router.get("/preview/{preview_id}/{page}")
def get_inpainted_preview(preview_id: str, page: int):
	"""
	Serve high-quality preview image for given preview id and 1-based page index.
	"""
	dir_path = PREVIEWS_DIR / preview_id
	if not dir_path.exists():
		raise HTTPException(status_code=404, detail="미리보기를 찾을 수 없습니다.")
	# filenames: page_001.png ...
	filename = f"page_{page:03d}.png"
	path = dir_path / filename
	if not path.exists():
		raise HTTPException(status_code=404, detail="페이지를 찾을 수 없습니다.")
	return FileResponse(path, media_type="image/png", filename=filename)


@router.get("/preview/{preview_id}/{page}/text/{text_index}")
def get_text_overlay(preview_id: str, page: int, text_index: int):
	"""
	Serve transparent text overlay image for given preview id, page, and text block index.
	"""
	dir_path = PREVIEWS_DIR / f"{preview_id}_text"
	if not dir_path.exists():
		raise HTTPException(status_code=404, detail="텍스트 오버레이를 찾을 수 없습니다.")
	filename = f"page_{page:03d}_text_{text_index:03d}.png"
	path = dir_path / filename
	if not path.exists():
		raise HTTPException(status_code=404, detail="텍스트 오버레이를 찾을 수 없습니다.")
	return FileResponse(path, media_type="image/png", filename=filename)


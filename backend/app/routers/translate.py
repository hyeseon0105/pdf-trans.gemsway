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

	# Extract text
	try:
		text = extract_text_from_pdf(upload_path)
	except Exception as e:
		raise HTTPException(status_code=400, detail=f"PDF 텍스트 추출 실패: {e}")

	if not text.strip():
		raise HTTPException(status_code=400, detail="PDF에서 추출 가능한 텍스트가 없습니다.")

	# Extract layout blocks (positions) for overlay preview
	# Try PyMuPDF first, fallback to OCR if no blocks found or too few blocks
	try:
		layout = extract_layout_blocks(upload_path)
		total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))
		# Count non-empty text blocks
		non_empty_blocks = sum(
			len([b for b in p.get("blocks", []) if (b.get("text", "") or "").strip()])
			for p in layout.get("pages", [])
		)
		
		# If too few blocks extracted, try OCR as supplement
		# OCR is more reliable for complex layouts and images
		# Lower threshold to catch more cases (5 -> 10)
		if total_blocks == 0 or non_empty_blocks < 10:
			print(f"PyMuPDF extracted {total_blocks} blocks ({non_empty_blocks} non-empty), trying OCR...")
			try:
				ocr_layout = extract_layout_blocks_ocr(upload_path)
				ocr_blocks = sum(len(p.get("blocks", [])) for p in ocr_layout.get("pages", []))
				ocr_non_empty = sum(
					len([b for b in p.get("blocks", []) if (b.get("text", "") or "").strip()])
					for p in ocr_layout.get("pages", [])
				)
				print(f"OCR extracted {ocr_blocks} blocks ({ocr_non_empty} non-empty)")
				
				# Use OCR if it found more blocks
				if ocr_non_empty > non_empty_blocks:
					print(f"Using OCR layout (found more blocks: {ocr_non_empty} > {non_empty_blocks})")
					layout = ocr_layout
				elif total_blocks == 0:
					# If PyMuPDF found nothing, use OCR even if it's not perfect
					print(f"Using OCR layout (PyMuPDF found no blocks)")
					layout = ocr_layout
			except Exception as e:
				print(f"OCR fallback failed: {e}")
				if total_blocks == 0:
					layout = {"pages": []}
		else:
			print(f"Using PyMuPDF layout ({total_blocks} blocks, {non_empty_blocks} non-empty)")
	except Exception as e:
		print(f"Error extracting layout blocks: {e}")
		# Try OCR as last resort
		try:
			layout = extract_layout_blocks_ocr(upload_path)
			print("Using OCR layout (PyMuPDF failed)")
		except Exception:
			layout = {"pages": []}

	# Translate full text once
	try:
		translated = translate_text(text, target_lang="ko")
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 실패: {e}")

	# Map translated text to each layout block
	# If blocks exist, map paragraph by paragraph; otherwise create synthetic blocks
	try:
		def _normalize(value: str) -> str:
			return " ".join((value or "").split())

		def _split_sentences(value: str) -> list[str]:
			return [seg.strip() for seg in re.split(r'(?<=[.!?\u3002\uFF01\uFF1F])\s+', value) if seg.strip()]

		def _add_pairs(origin_list: list[str], translated_list: list[str], table: dict[str, str]):
			for origin_text, translated_text in zip(origin_list, translated_list):
				key = _normalize(origin_text)
				if key and key not in table:
					table[key] = translated_text.strip()

		translation_cache: dict[str, str] = {}
		translation_lookup: dict[str, str] = {}
		unmatched_entries: list[tuple[str, dict]] = []

		total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))

		if total_blocks > 0:
			# Build lookup table with multiple granularities
			original_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
			translated_paragraphs = [p.strip() for p in translated.split("\n\n") if p.strip()]
			original_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
			translated_lines = [ln.strip() for ln in translated.splitlines() if ln.strip()]
			original_sentences = _split_sentences(text)
			translated_sentences = _split_sentences(translated)

			_add_pairs(original_paragraphs, translated_paragraphs, translation_lookup)
			_add_pairs(original_lines, translated_lines, translation_lookup)
			_add_pairs(original_sentences, translated_sentences, translation_lookup)

			lookup_items = list(translation_lookup.items())

			for page in layout.get("pages", []):
				for block in page.get("blocks", []):
					original_text = (block.get("text", "") or "").strip()
					if not original_text:
						block["translated_text"] = ""
						continue

					normalized_text = _normalize(original_text)
					if not normalized_text:
						block["translated_text"] = ""
						continue

					# direct match
					if normalized_text in translation_lookup:
						block["translated_text"] = translation_lookup[normalized_text]
						continue

					# fuzzy match (lower threshold for better matching)
					best_value = ""
					best_score = 0.0
					for key, value in lookup_items:
						score = SequenceMatcher(None, normalized_text.lower(), key.lower()).ratio()
						if score > best_score:
							best_score = score
							best_value = value
					# Lower threshold from 0.45 to 0.3 for better matching
					if best_value and best_score >= 0.3 and _normalize(best_value).lower() != normalized_text.lower():
						translation_lookup[normalized_text] = best_value
						block["translated_text"] = best_value
						continue

					# If no match found, add to unmatched entries for individual translation
					# This ensures ALL text blocks get translated, even if matching fails
					unmatched_entries.append((normalized_text, {"original": original_text, "block": block}))

			if unmatched_entries:
				print(f"Found {len(unmatched_entries)} unmatched text blocks, translating with context...")
				pending: dict[str, dict] = {}
				for norm, payload in unmatched_entries:
					if norm not in pending:
						pending[norm] = {"original": payload["original"], "blocks": []}
					pending[norm]["blocks"].append(payload["block"])

				# Group blocks by page and position to maintain context
				# This helps translate related blocks together for better flow
				page_block_groups: dict[int, list[dict]] = {}
				for norm, info in pending.items():
					for blk in info["blocks"]:
						# Find which page this block belongs to
						page_idx = -1
						for idx, page in enumerate(layout.get("pages", [])):
							if blk in page.get("blocks", []):
								page_idx = idx
								break
						if page_idx not in page_block_groups:
							page_block_groups[page_idx] = []
						page_block_groups[page_idx].append({
							"block": blk,
							"original": info["original"],
							"normalized": norm
						})

				# Translate blocks with context from the same page
				for page_idx, block_group in page_block_groups.items():
					# Try to find context from surrounding blocks in the original text
					context_blocks = []
					for item in block_group:
						context_blocks.append(item["original"])
					
					# Combine context blocks with some spacing
					context_text = " ".join(context_blocks)
					
					# Try to find this context in the original full text for better matching
					context_normalized = _normalize(context_text)
					
					# Check if we can find a better match in the translated text
					best_context_match = None
					best_context_score = 0.0
					
					# Look for similar text in original paragraphs (including partial matches)
					for orig_para, trans_para in zip(original_paragraphs, translated_paragraphs):
						orig_normalized = _normalize(orig_para)
						# Check if context is contained in paragraph or vice versa
						if context_normalized.lower() in orig_normalized.lower():
							# Context is part of this paragraph, use the translation
							best_context_score = 1.0
							best_context_match = trans_para
							break
						elif orig_normalized.lower() in context_normalized.lower():
							# Paragraph is part of context, use the translation
							score = len(orig_normalized) / len(context_normalized) if context_normalized else 0
							if score > best_context_score:
								best_context_score = score
								best_context_match = trans_para
						else:
							# Use similarity score
							score = SequenceMatcher(None, context_normalized.lower(), orig_normalized.lower()).ratio()
							if score > best_context_score and score > 0.5:
								best_context_score = score
								best_context_match = trans_para
					
					# Also check individual blocks against sentences for better matching
					for item in block_group:
						norm = item["normalized"]
						segment = item["original"]
						
						# Try to find partial match in translated sentences
						best_sentence_match = None
						best_sentence_score = 0.0
						segment_normalized = _normalize(segment)
						
						for orig_sent, trans_sent in zip(original_sentences, translated_sentences):
							orig_sent_normalized = _normalize(orig_sent)
							if segment_normalized.lower() in orig_sent_normalized.lower():
								best_sentence_score = 1.0
								best_sentence_match = trans_sent
								break
							else:
								score = SequenceMatcher(None, segment_normalized.lower(), orig_sent_normalized.lower()).ratio()
								if score > best_sentence_score and score > 0.6:
									best_sentence_score = score
									best_sentence_match = trans_sent
						
						if best_sentence_match and best_sentence_score > 0.6:
							item["block"]["translated_text"] = best_sentence_match
							translation_lookup[norm] = best_sentence_match
						elif best_context_match and best_context_score > 0.5:
							# Use context match if available
							item["block"]["translated_text"] = best_context_match
							translation_lookup[norm] = best_context_match
						else:
							# Translate individually with context awareness
							if norm in translation_lookup:
								translated_snippet = translation_lookup[norm]
							elif norm in translation_cache:
								translated_snippet = translation_cache[norm]
							else:
								try:
									# Try to translate with surrounding context if available
									if len(context_blocks) > 1 and len(context_text) < 2000:
										# Translate the whole context group for better flow
										context_segment = " ".join(context_blocks)
										print(f"Translating block group with context ({len(context_segment)} chars): '{context_segment[:100]}...'")
										context_translated = translate_text(context_segment, target_lang="ko")
										# Use the context translation for this block
										translated_snippet = context_translated
										translation_cache[norm] = translated_snippet
										translation_lookup[norm] = translated_snippet
									else:
										# Single block, translate individually
										print(f"Translating unmatched block ({len(segment)} chars): '{segment[:100]}...'")
										translated_snippet = translate_text(segment, target_lang="ko")
										print(f"Translation result ({len(translated_snippet)} chars): '{translated_snippet[:100]}...'")
										if not translated_snippet.strip():
											print(f"Warning: Translation returned empty for block: '{segment[:50]}...'")
											translated_snippet = segment  # Fallback to original
										translation_cache[norm] = translated_snippet
										translation_lookup[norm] = translated_snippet
								except Exception as e:
									print(f"Failed to translate unmatched block: {e}")
									import traceback
									traceback.print_exc()
									translated_snippet = segment  # Fallback to original
									translation_cache[norm] = translated_snippet
									translation_lookup[norm] = translated_snippet
							item["block"]["translated_text"] = translated_snippet
				
				print(f"Translated {len(pending)} unmatched text blocks (total {sum(len(info['blocks']) for info in pending.values())} blocks updated)")
		else:
			# No blocks -> create synthetic blocks with translated text
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
	except Exception:
		# 레이아웃 매핑 실패 시 layout은 빈 상태로 반환
		pass

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


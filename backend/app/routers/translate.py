import re
import uuid
from pathlib import Path
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
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
async def translate_pdf(
	file: UploadFile = File(...),
	use_finetuned: Optional[str] = Form(None),
	finetuned_model_id: Optional[str] = Form(None)
):
	"""
	PDF 번역 엔드포인트
	
	Args:
		file: PDF 파일
		use_finetuned: 파인튜닝 모델 사용 여부 ("true" 문자열 또는 None, 기본값: False, 항상 gpt-4o-mini 사용)
		finetuned_model_id: 파인튜닝 모델 ID (use_finetuned="true"일 때 필수)
	"""
	if file.content_type != "application/pdf":
		raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")
	
	# FormData에서 받은 문자열을 boolean으로 변환
	use_finetuned_bool = use_finetuned and use_finetuned.lower() == "true"
	
	# 파인튜닝 모델 사용 시 모델 ID 확인
	if use_finetuned_bool and not finetuned_model_id:
		raise HTTPException(status_code=400, detail="파인튜닝 모델을 사용하려면 finetuned_model_id가 필요합니다.")

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
			# 배치 번역을 위한 블록 수집
			# 작은 블록들을 묶어서 한 번에 번역하여 속도 향상
			all_blocks_info: list[tuple[int, int, dict, str]] = []  # (page_idx, block_idx, block, text)
			
			for page_idx, page in enumerate(layout.get("pages", [])):
				blocks = page.get("blocks", [])
				for block_idx, block in enumerate(blocks):
					original_text = (block.get("text", "") or "").strip()
					if original_text:
						normalized_text = _normalize(original_text)
						if normalized_text:
							all_blocks_info.append((page_idx, block_idx, block, original_text))
			
			# 배치 크기 설정: 작은 블록들을 묶어서 번역 (최대 3000자까지)
			batch_size = 3000
			current_batch: list[tuple[int, int, dict, str]] = []
			current_batch_size = 0
			
			def _translate_batch(batch: list[tuple[int, int, dict, str]], batch_num: int) -> dict[tuple[int, int], str]:
				"""배치의 블록들을 한 번에 번역"""
				if not batch:
					return {}
				
				# 배치의 모든 텍스트를 하나로 묶기
				batch_texts = [text for _, _, _, text in batch]
				combined_text = "\n\n---BLOCK_SEPARATOR---\n\n".join(batch_texts)
				
				translation_instructions = (
					"다음 영어 텍스트들을 자연스러운 한국어로 번역해주세요.\n\n"
					"번역 원칙:\n"
					"1. 【직역 금지】 의미를 정확히 전달하는 자연스러운 한국어로 의역\n"
					"2. 【자연스러운 어순】 한국어 어순에 맞게 문장 구조 재배치\n"
					"3. 【읽기 쉽게】 전문 용어도 이해하기 쉽게 번역\n"
					"4. 【문맥 고려】 문맥에 맞는 적절한 한국어 표현 사용\n"
					"5. 【구조 유지】 문단, 줄바꿈, 리스트 구조는 원본과 동일하게\n"
					"6. 【완전성】 모든 내용 번역, 추가 내용 없음\n"
					"7. 【자연스러운 종결】 제목은 체언형, 본문은 '~합니다/됩니다/있습니다' 등 자연스러운 종결어미 사용\n\n"
					"---BLOCK_SEPARATOR---로 구분된 각 텍스트 블록을 개별적으로 번역하고, "
					"번역 결과도 동일한 구분자로 구분해주세요.\n\n"
					f"번역할 텍스트:\n{combined_text}"
				)
				
				try:
					translated_batch = translate_text(
						translation_instructions, 
						target_lang="ko",
						use_finetuned=use_finetuned_bool,
						finetuned_model_id=finetuned_model_id
					)
					
					# 구분자로 분리
					translated_parts = translated_batch.split("---BLOCK_SEPARATOR---")
					
					# 결과 매핑
					result = {}
					for idx, (page_idx, block_idx, block, _) in enumerate(batch):
						if idx < len(translated_parts):
							translated_text = translated_parts[idx].strip()
							# 구분자 주변의 공백/줄바꿈 제거
							translated_text = re.sub(r'^[\s\n\-]+|[\s\n\-]+$', '', translated_text)
							result[(page_idx, block_idx)] = translated_text
						else:
							# 번역 결과가 부족하면 개별 번역 시도
							try:
								simple_prompt = translation_instructions.split("번역할 텍스트:")[0] + f"번역할 텍스트:\n{batch[idx][3]}"
								result[(page_idx, block_idx)] = translate_text(
									simple_prompt, 
									target_lang="ko",
									use_finetuned=use_finetuned_bool,
									finetuned_model_id=finetuned_model_id
								).strip()
							except:
								result[(page_idx, block_idx)] = ""
					
					return result
				except Exception as e:
					print(f"Error translating batch {batch_num}: {e}")
					# 배치 실패 시 개별 번역으로 폴백
					result = {}
					for page_idx, block_idx, block, text in batch:
						try:
							simple_prompt = (
								"다음 영어 텍스트를 자연스러운 한국어로 번역해주세요.\n\n"
								f"번역할 텍스트:\n{text}"
							)
							result[(page_idx, block_idx)] = translate_text(
								simple_prompt, 
								target_lang="ko",
								use_finetuned=use_finetuned_bool,
								finetuned_model_id=finetuned_model_id
							).strip()
						except:
							result[(page_idx, block_idx)] = ""
					return result
			
			# 배치 단위로 번역 처리
			translated_results: dict[tuple[int, int], str] = {}
			batch_num = 0
			
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
					
					# 큰 블록(300자 이상)은 개별 번역
					if len(original_text) >= 300:
						# 현재 배치가 있으면 먼저 처리
						if current_batch:
							batch_num += 1
							batch_results = _translate_batch(current_batch, batch_num)
							translated_results.update(batch_results)
							current_batch = []
							current_batch_size = 0
						
						# 큰 블록은 개별 번역
						try:
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
								f"번역할 텍스트:\n{original_text}"
							)
							translated_block = translate_text(
								translation_instructions, 
								target_lang="ko",
								use_finetuned=use_finetuned_bool,
								finetuned_model_id=finetuned_model_id
							)
							# 마커 제거
							translated_block = re.sub(r'\[번역할 텍스트\]:?\s*', '', translated_block)
							translated_block = re.sub(r'^(Text to translate|번역할 텍스트):?\s*', '', translated_block, flags=re.IGNORECASE)
							translated_block = translated_block.strip()
							translated_results[(page_idx, block_idx)] = translated_block
						except Exception as e:
							print(f"Error translating large block: {e}")
							translated_results[(page_idx, block_idx)] = ""
					else:
						# 작은 블록은 배치에 추가
						text_len = len(original_text)
						if current_batch_size + text_len > batch_size and current_batch:
							# 배치가 가득 찼으면 번역
							batch_num += 1
							batch_results = _translate_batch(current_batch, batch_num)
							translated_results.update(batch_results)
							current_batch = []
							current_batch_size = 0
						
						current_batch.append((page_idx, block_idx, block, original_text))
						current_batch_size += text_len + 50  # 구분자 공간 고려
				
				# 페이지가 끝날 때 현재 배치 처리
				if current_batch:
					batch_num += 1
					batch_results = _translate_batch(current_batch, batch_num)
					translated_results.update(batch_results)
					current_batch = []
					current_batch_size = 0
			
			# 남은 배치 처리
			if current_batch:
				batch_num += 1
				batch_results = _translate_batch(current_batch, batch_num)
				translated_results.update(batch_results)
			
			# 결과를 블록에 할당
			for page_idx, page in enumerate(layout.get("pages", [])):
				blocks = page.get("blocks", [])
				for block_idx, block in enumerate(blocks):
					original_text = (block.get("text", "") or "").strip()
					if not original_text:
						continue
					
					key = (page_idx, block_idx)
					if key in translated_results:
						translated_block = translated_results[key]
						block["translated_text"] = translated_block
						if translated_block:
							translated_blocks_text.append(translated_block)
							translated_blocks_by_position.append(translated_block)
					else:
						block["translated_text"] = ""
						translated_blocks_by_position.append("")
			
			# Create full translated text from blocks (for compatibility with existing code)
			translated = "\n\n".join(translated_blocks_text)
		else:
			# No blocks -> translate full text and create synthetic blocks
			try:
				translated = translate_text(
					text, 
					target_lang="ko",
					use_finetuned=use_finetuned_bool,
					finetuned_model_id=finetuned_model_id
				)
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
			translated = translate_text(
				text, 
				target_lang="ko",
				use_finetuned=use_finetuned_bool,
				finetuned_model_id=finetuned_model_id
			)
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
		
		# 번역문이 없으면 번역 수행 (기본 모델 사용)
		if not request.translated_text:
			translated_text = translate_text(original_text, target_lang="ko", use_finetuned=False)
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


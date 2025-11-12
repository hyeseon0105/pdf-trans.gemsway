import re
import uuid
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from ..config import UPLOADS_DIR, TRANSLATED_DIR
from ..services.pdf_utils import (
	extract_text_from_pdf,
	create_pdf_from_text,
	extract_layout_blocks,
	extract_layout_blocks_ocr,
)
from ..services.translate_service import translate_text

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
	# Try PyMuPDF first, fallback to OCR if no blocks found
	try:
		layout = extract_layout_blocks(upload_path)
		total_blocks = sum(len(p.get("blocks", [])) for p in layout.get("pages", []))
		if total_blocks == 0:
			try:
				layout = extract_layout_blocks_ocr(upload_path)
			except Exception:
				layout = {"pages": []}
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

					# fuzzy match
					best_value = ""
					best_score = 0.0
					for key, value in lookup_items:
						score = SequenceMatcher(None, normalized_text.lower(), key.lower()).ratio()
						if score > best_score:
							best_score = score
							best_value = value
					if best_value and best_score >= 0.45 and _normalize(best_value).lower() != normalized_text.lower():
						translation_lookup[normalized_text] = best_value
						block["translated_text"] = best_value
						continue

					unmatched_entries.append((normalized_text, {"original": original_text, "block": block}))

			if unmatched_entries:
				pending: dict[str, dict] = {}
				for norm, payload in unmatched_entries:
					if norm not in pending:
						pending[norm] = {"original": payload["original"], "blocks": []}
					pending[norm]["blocks"].append(payload["block"])

				for norm, info in pending.items():
					if norm in translation_lookup:
						translated_snippet = translation_lookup[norm]
					elif norm in translation_cache:
						translated_snippet = translation_cache[norm]
					else:
						segment = info["original"]
						try:
							translated_snippet = translate_text(segment, target_lang="ko")
						except Exception:
							translated_snippet = segment
						translation_cache[norm] = translated_snippet
						translation_lookup[norm] = translated_snippet
					for blk in info["blocks"]:
						blk["translated_text"] = translated_snippet
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

	# Generate translated PDF (simple text PDF for download fallback)
	file_id = str(uuid.uuid4())
	output_path = TRANSLATED_DIR / f"{file_id}.pdf"
	try:
		create_pdf_from_text(translated, output_path)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 PDF 생성 실패: {e}")

	return {
		"upload_id": upload_id,
		"file_id": file_id,
		"translated_text": translated,
		"layout": layout,
	}


@router.get("/download/{file_id}")
def download_pdf(file_id: str):
	path = TRANSLATED_DIR / f"{file_id}.pdf"
	if not path.exists():
		raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
	return FileResponse(path, filename="translated.pdf", media_type="application/pdf")


@router.get("/uploads/{upload_id}")
def get_uploaded_pdf(upload_id: str):
	path = UPLOADS_DIR / f"{upload_id}.pdf"
	if not path.exists():
		raise HTTPException(status_code=404, detail="업로드 파일을 찾을 수 없습니다.")
	return FileResponse(path, filename="original.pdf", media_type="application/pdf")



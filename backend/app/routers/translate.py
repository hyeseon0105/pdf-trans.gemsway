import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from ..config import UPLOADS_DIR, TRANSLATED_DIR
from ..services.pdf_utils import extract_text_from_pdf, create_pdf_from_text
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

	# Translate
	try:
		translated = translate_text(text, target_lang="ko")
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 실패: {e}")

	# Generate translated PDF
	file_id = str(uuid.uuid4())
	output_path = TRANSLATED_DIR / f"{file_id}.pdf"
	try:
		create_pdf_from_text(translated, output_path)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"번역 PDF 생성 실패: {e}")

	return {
		"file_id": file_id,
		"translated_text": translated,
	}


@router.get("/download/{file_id}")
def download_pdf(file_id: str):
	path = TRANSLATED_DIR / f"{file_id}.pdf"
	if not path.exists():
		raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
	return FileResponse(
		path,
		filename="translated.pdf",
		media_type="application/pdf",
	)



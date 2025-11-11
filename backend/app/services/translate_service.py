import os
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[translate_service] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False

# OpenAI SDK (optional)
try:
	from openai import OpenAI  # type: ignore
except Exception:
	OpenAI = None  # type: ignore

# Google Cloud Translate (optional)
try:
	from google.cloud import translate_v2 as google_translate  # type: ignore
except Exception:
	google_translate = None  # type: ignore

_openai_client: Optional["OpenAI"] = None
_gcp_client: Optional["google_translate.Client"] = None  # type: ignore


def _get_openai_client() -> Optional["OpenAI"]:
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if OpenAI is None:
        logger.error("OpenAI SDK를 로드하지 못했습니다. 패키지가 설치되었는지 확인하세요.")
        return None
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        return None
    try:
        _openai_client = OpenAI(api_key=api_key)
        return _openai_client
    except Exception as exc:
        logger.error("OpenAI 클라이언트 생성 실패: %s", exc, exc_info=True)
        return None


def _get_gcp_client() -> Optional["google_translate.Client"]:  # type: ignore
    global _gcp_client
    if _gcp_client is not None:
        return _gcp_client
    if google_translate is None:
        logger.error("google-cloud-translate 패키지를 로드하지 못했습니다.")
        return None
    # Requires GOOGLE_APPLICATION_CREDENTIALS to point to a service account JSON
    try:
        _gcp_client = google_translate.Client()  # type: ignore
        return _gcp_client
    except Exception as exc:
        logger.error("Google Cloud Translate 클라이언트 생성 실패: %s", exc, exc_info=True)
        return None


def _chunk_paragraphs(text: str, max_chunk_chars: int = 6000) -> List[str]:
	"""
	Split text into chunks at paragraph boundaries (double newline) to avoid model limits,
	while preserving paragraph structure.
	"""
	paragraphs = text.split("\n\n")
	chunks: List[str] = []
	current: List[str] = []
	current_len = 0
	for p in paragraphs:
		plen = len(p)
		# +2 accounts for the joining "\n\n"
		if current_len + plen + (2 if current else 0) > max_chunk_chars and current:
			chunks.append("\n\n".join(current))
			current = [p]
			current_len = plen
		else:
			current.append(p)
			current_len += (2 if current_len > 0 else 0) + plen
	if current:
		chunks.append("\n\n".join(current))
	return chunks


def _translate_with_openai(text: str, target_lang: str = "ko") -> Optional[str]:
	client = _get_openai_client()
	if client is None:
		return None
	model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
	chunks = _chunk_paragraphs(text)
	outputs: List[str] = []
	for chunk in chunks:
		prompt = (
			f"Translate the following English text into natural {target_lang} (Korean).\n"
			f"- Preserve paragraph and newline structure exactly.\n"
			f"- Do not add notes, headers, or explanations.\n"
			f"- Return only the translated text.\n\n"
			f"Text:\n{chunk}"
		)
		try:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a professional translator."},
					{"role": "user", "content": prompt},
				],
				temperature=0.2,
			)
			content = resp.choices[0].message.content if resp.choices else ""
			outputs.append(content or "")
		except Exception as exc:
			logger.error("OpenAI translation chunk 실패: %s", exc, exc_info=True)
			# If one chunk fails, bail out to fallback method
			return None
	return "\n\n".join(outputs).strip()


def _translate_with_google_cloud(text: str, target_lang: str = "ko") -> Optional[str]:
	client = _get_gcp_client()
	if client is None:
		return None
	# Translate paragraph by paragraph to preserve structure better
	chunks = _chunk_paragraphs(text, max_chunk_chars=4500)
	outputs: List[str] = []
	try:
		for c in chunks:
			res = client.translate(c, target_language=target_lang, format_="text")  # type: ignore
			translated = res.get("translatedText", "") if isinstance(res, dict) else ""
			outputs.append(translated or "")
		return "\n\n".join(outputs).strip()
	except Exception as exc:
		logger.error("Google Cloud translation 실패: %s", exc, exc_info=True)
		return None


def translate_text(text: str, target_lang: str = "ko") -> str:
	"""
	Translate text using provider specified by TRANSLATION_PROVIDER.
	Supported providers:
	- openai (requires OPENAI_API_KEY, optional OPENAI_MODEL)
	- google (Google Cloud Translate; requires GOOGLE_APPLICATION_CREDENTIALS)
	"""
	text = text or ""
	if not text.strip():
		return text

	provider = os.environ.get("TRANSLATION_PROVIDER", "openai").lower()

	if provider == "openai":
		translated = _translate_with_openai(text, target_lang=target_lang)
		if translated is not None and translated.strip():
			return translated
		fallback = _translate_with_google_cloud(text, target_lang=target_lang)
		if fallback is not None and fallback.strip():
			return fallback
		raise RuntimeError(
			"OpenAI 번역 사용을 위해 `OPENAI_API_KEY`를 설정하거나, `TRANSLATION_PROVIDER`를 `google`로 변경하세요."
		)
	else:
		translated = _translate_with_google_cloud(text, target_lang=target_lang)
		if translated is not None and translated.strip():
			return translated
		raise RuntimeError(
			"Google Cloud 번역 사용을 위해 `GOOGLE_APPLICATION_CREDENTIALS`를 설정하거나, `TRANSLATION_PROVIDER`를 `openai`로 변경하세요."
		)



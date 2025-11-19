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
			f"다음 영어 텍스트를 자연스러운 한국어로 번역해주세요.\n\n"
			f"번역 원칙:\n"
			f"1. 【직역 금지】 단어 하나하나를 직역하지 말고, 의미를 정확히 전달하는 자연스러운 한국어로 번역\n"
			f"2. 【자연스러운 어순】 한국어 어순과 표현 방식에 맞게 문장 구조 재배치\n"
			f"3. 【읽기 쉽게】 전문 용어도 한국 독자가 이해하기 쉽게 설명적으로 번역\n"
			f"4. 【문맥 고려】 문맥을 파악하여 가장 적절한 한국어 표현 사용\n"
			f"5. 【구조 유지】 문단 구분, 줄바꿈, 리스트 구조는 원본과 동일하게 유지\n"
			f"6. 【완전성】 모든 내용을 빠짐없이 번역하되, 불필요한 내용 추가하지 않기\n"
			f"7. 【자연스러운 종결】 제목은 체언형(명사형), 본문은 '~합니다/됩니다/있습니다' 등 문맥에 맞는 자연스러운 종결어미 사용\n"
			f"8. 【기술 문서】 전문성을 유지하되 딱딱하지 않고 읽기 편한 설명투로 작성\n\n"
			f"번역할 텍스트:\n{chunk}"
		)
		try:
			resp = client.chat.completions.create(
				model=model,
				messages=[
					{
						"role": "system", 
						"content": (
							"당신은 10년 경력의 전문 기술 번역가입니다. "
							"영어를 자연스러운 한국어로 의역하는 것이 핵심입니다. "
							"직역은 절대 금지되며, 한국 독자가 읽기 편한 자연스러운 표현을 사용합니다. "
							"기술 용어는 필요시 부연 설명을 추가하여 이해하기 쉽게 만듭니다. "
							"문장 구조는 한국어 어순에 맞게 재배치하고, 어색한 표현은 자연스럽게 다듬습니다. "
							"전문성을 유지하되 딱딱하지 않은 설명투로 작성하여 독자가 편안하게 읽을 수 있도록 합니다. "
							"모든 내용을 완전히 번역하되, 원본에 없는 내용은 추가하지 않습니다."
						)
					},
					{"role": "user", "content": prompt},
				],
				temperature=0.3,  # 자연스러운 표현을 위해 약간 높임
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



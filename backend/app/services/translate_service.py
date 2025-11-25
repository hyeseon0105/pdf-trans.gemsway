import os
import logging
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def _translate_with_openai(text: str, target_lang: str = "ko", use_finetuned: bool = False, finetuned_model_id: Optional[str] = None) -> Optional[str]:
	client = _get_openai_client()
	if client is None:
		return None
	
	# 기본 모델은 항상 gpt-4o-mini로 고정
	# 파인튜닝 모델은 use_finetuned=True이고 finetuned_model_id가 제공될 때만 사용
	if use_finetuned and finetuned_model_id:
		model = finetuned_model_id
		logger.info(f"파인튜닝 모델 사용: {model}")
	else:
		model = "gpt-4o-mini"
		logger.info(f"기본 모델 사용: {model}")
	chunks = _chunk_paragraphs(text)
	
	# 병렬 처리를 위한 헬퍼 함수
	def _translate_chunk(chunk: str, chunk_idx: int, model_to_use: str) -> tuple[int, Optional[str]]:
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
			f"8. 【브로셔 톤】 병원/의료 서비스 브로셔나 소개 자료에 쓸 수 있을 정도로 자연스럽고 매끄러운 문체로 번역하되, 지나치게 가볍지 않게 품위 있게 작성\n"
			f"9. 【문단 단위 번역】 한 문장씩 기계적으로 번역하지 말고, 문단 전체를 하나의 덩어리로 보고 문맥을 고려해 자연스럽게 다시 쓰기\n\n"
			f"번역할 텍스트:\n{chunk}"
		)
		try:
			resp = client.chat.completions.create(
				model=model_to_use,
				messages=[
					{
						"role": "system", 
						"content": (
							"당신은 10년 경력의 전문 번역가이자 브로셔/홍보 카피라이팅에 능숙한 전문가입니다. "
							"영어를 자연스럽고 매끄러운 한국어로 의역하는 것이 핵심입니다. "
							"직역은 절대 금지되며, 한국 독자가 읽기 편한 자연스러운 표현을 사용합니다. "
							"기술/의료 용어는 필요시 짧은 부연 설명을 덧붙여 이해하기 쉽게 만듭니다. "
							"문단 전체의 흐름과 맥락을 먼저 파악한 뒤, 문장 구조를 한국어 어순에 맞게 재배치하고 자연스럽게 다듬습니다. "
							"병원·의료 서비스 브로셔에 실릴 수 있을 정도로 세련되고 품위 있는 문체를 유지하되, 과장되거나 가벼운 표현은 피합니다. "
							"모든 내용을 완전히 번역하되, 원본에 없는 정보를 새로 추가하거나 왜곡하지 않습니다."
						)
					},
					{"role": "user", "content": prompt},
				],
				temperature=0.35,  # 자연스럽고 매끄러운 표현을 위해 약간의 다양성 허용
			)
			content = resp.choices[0].message.content if resp.choices else ""
			return (chunk_idx, content or "")
		except Exception as exc:
			error_msg = str(exc).lower()
			error_type = type(exc).__name__
			
			# 할당량 초과 오류 명확히 표시
			if "ratelimit" in error_msg or "429" in error_msg or "quota" in error_msg or error_type == "RateLimitError":
				logger.error("OpenAI API 할당량 초과: %s", exc)
				raise RuntimeError(
					"OpenAI API 할당량이 초과되었습니다. "
					"OpenAI 계정의 사용량 및 결제 정보를 확인하거나, "
					"잠시 후 다시 시도하세요. "
					"또는 `TRANSLATION_PROVIDER`를 `google`로 변경하여 Google Cloud Translate를 사용할 수 있습니다."
				) from exc
			
			# 모델이 존재하지 않는 경우 기본 모델로 재시도
			if "model" in error_msg and ("not found" in error_msg or "invalid" in error_msg or "does not exist" in error_msg):
				logger.warning(f"모델 '{model_to_use}'이 존재하지 않습니다. 기본 모델로 재시도합니다: {exc}")
				# 기본 모델로 재시도 (한 번만)
				if model_to_use != "gpt-4o-mini":
					try:
						resp = client.chat.completions.create(
							model="gpt-4o-mini",
							messages=[
								{
									"role": "system", 
									"content": (
										"당신은 10년 경력의 전문 번역가이자 브로셔/홍보 카피라이팅에 능숙한 전문가입니다. "
										"영어를 자연스럽고 매끄러운 한국어로 의역하는 것이 핵심입니다. "
										"직역은 절대 금지되며, 한국 독자가 읽기 편한 자연스러운 표현을 사용합니다. "
										"기술/의료 용어는 필요시 짧은 부연 설명을 덧붙여 이해하기 쉽게 만듭니다. "
										"문단 전체의 흐름과 맥락을 먼저 파악한 뒤, 문장 구조를 한국어 어순에 맞게 재배치하고 자연스럽게 다듬습니다. "
										"병원·의료 서비스 브로셔에 실릴 수 있을 정도로 세련되고 품위 있는 문체를 유지하되, 과장되거나 가벼운 표현은 피합니다. "
										"모든 내용을 완전히 번역하되, 원본에 없는 정보를 새로 추가하거나 왜곡하지 않습니다."
									)
								},
								{"role": "user", "content": prompt},
							],
							temperature=0.35,
						)
						content = resp.choices[0].message.content if resp.choices else ""
						return (chunk_idx, content or "")
					except Exception as retry_exc:
						logger.error("기본 모델로 재시도 실패: %s", retry_exc, exc_info=True)
						return (chunk_idx, None)
				else:
					return (chunk_idx, None)
			else:
				logger.error("OpenAI translation chunk 실패: %s", exc, exc_info=True)
				return (chunk_idx, None)
	
	# 병렬 처리: 최대 5개의 청크를 동시에 번역
	# OpenAI API rate limit을 고려하여 동시 요청 수를 제한
	max_workers = min(5, len(chunks))
	outputs: List[Optional[str]] = [None] * len(chunks)
	
	if len(chunks) == 1:
		# 청크가 하나면 병렬 처리 불필요
		_, result = _translate_chunk(chunks[0], 0, model)
		if result is None:
			return None
		return result.strip()
	
	# 여러 청크를 병렬로 처리
	with ThreadPoolExecutor(max_workers=max_workers) as executor:
		future_to_chunk = {
			executor.submit(_translate_chunk, chunk, idx, model): idx 
			for idx, chunk in enumerate(chunks)
		}
		
		for future in as_completed(future_to_chunk):
			chunk_idx, result = future.result()
			outputs[chunk_idx] = result
	
	# None이 있으면 실패한 청크가 있음
	if any(x is None for x in outputs):
		logger.error("일부 청크 번역 실패")
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


def translate_text(text: str, target_lang: str = "ko", use_finetuned: bool = False, finetuned_model_id: Optional[str] = None) -> str:
	"""
	Translate text using provider specified by TRANSLATION_PROVIDER.
	Supported providers:
	- openai (requires OPENAI_API_KEY, always uses gpt-4o-mini unless use_finetuned=True)
	- google (Google Cloud Translate; requires GOOGLE_APPLICATION_CREDENTIALS)
	
	Args:
		text: Text to translate
		target_lang: Target language (default: "ko")
		use_finetuned: If True, use finetuned model (requires finetuned_model_id)
		finetuned_model_id: Finetuned model ID (e.g., "ft:gpt-3.5-turbo-0125:org:model:xxx")
	"""
	text = text or ""
	if not text.strip():
		return text

	provider = os.environ.get("TRANSLATION_PROVIDER", "openai").lower()

	if provider == "openai":
		translated = _translate_with_openai(text, target_lang=target_lang, use_finetuned=use_finetuned, finetuned_model_id=finetuned_model_id)
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



"""
번역 검수 및 보정 서비스
- 정확도 검증 (의미 일치율)
- 어투 보정
- 누락 문장 보완
"""
import re
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

try:
	from openai import OpenAI
	_openai_available = True
except Exception:
	_openai_available = False
	OpenAI = None


def _normalize_text(text: str) -> str:
	"""텍스트 정규화 (공백, 특수문자 정리)"""
	return " ".join(re.sub(r'[^\w\s]', ' ', text.lower()).split())


def _calculate_semantic_similarity(text1: str, text2: str) -> float:
	"""
	의미 유사도 계산 (0.0 ~ 1.0)
	간단한 버전: 정규화된 텍스트의 SequenceMatcher 사용
	향후 OpenAI embedding으로 개선 가능
	"""
	norm1 = _normalize_text(text1)
	norm2 = _normalize_text(text2)
	if not norm1 or not norm2:
		return 0.0
	return SequenceMatcher(None, norm1, norm2).ratio()


def _split_into_paragraphs(text: str) -> List[str]:
	"""텍스트를 문단 단위로 분리"""
	# 빈 줄로 구분된 문단
	paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
	# 문단이 없으면 줄 단위로
	if not paragraphs:
		paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
	return paragraphs


def _improve_tone(korean_text: str) -> str:
	"""
	어투 보정: 직역체를 자연스러운 한국어로
	"""
	improvements = {
		"의 부분입니다": "에 완벽히 통합되어 있습니다",
		"명확하고 연결된 보고서": "명확하고 통합된 맞춤 보고서",
		"제공합니다": "제공합니다",  # 기본 유지
		"설계되었습니다": "설계되었습니다",  # 기본 유지
	}
	
	result = korean_text
	for old, new in improvements.items():
		if old in result:
			result = result.replace(old, new)
	
	return result


def review_translation(original_text: str, translated_text: str) -> Dict:
	"""
	번역 검수 및 보정
	
	Returns:
		{
			"results": [
				{
					"english": "원문 문장",
					"korean": "번역문",
					"status": "ok / ⚠️ 불일치 / ❌ 미번역",
					"similarity": 0.85,
					"suggestion": "수정 제안"
				}
			],
			"summary": {
				"total_paragraphs": 100,
				"ok_count": 85,
				"warning_count": 10,
				"missing_count": 5,
				"accuracy_percent": 85.0
			}
		}
	"""
	original_paras = _split_into_paragraphs(original_text)
	translated_paras = _split_into_paragraphs(translated_text)
	
	results = []
	translated_used = set()
	
	# 1:1 매핑 시도
	for orig_idx, orig_para in enumerate(original_paras):
		best_match_idx = None
		best_similarity = 0.0
		
		# 번역된 문단 중 가장 유사한 것 찾기
		for trans_idx, trans_para in enumerate(translated_paras):
			if trans_idx in translated_used:
				continue
			similarity = _calculate_semantic_similarity(orig_para, trans_para)
			if similarity > best_similarity:
				best_similarity = similarity
				best_match_idx = trans_idx
		
		# 매핑 결정
		if best_match_idx is not None and best_similarity >= 0.8:
			# 정확도 OK
			matched_trans = translated_paras[best_match_idx]
			improved = _improve_tone(matched_trans)
			results.append({
				"english": orig_para,
				"korean": improved if improved != matched_trans else matched_trans,
				"status": "ok" if improved == matched_trans else "⚠️ 불일치",
				"similarity": round(best_similarity, 3),
				"suggestion": improved if improved != matched_trans else None
			})
			translated_used.add(best_match_idx)
		elif best_match_idx is not None and best_similarity >= 0.5:
			# 유사도 낮음 (0.5~0.8)
			matched_trans = translated_paras[best_match_idx]
			improved = _improve_tone(matched_trans)
			results.append({
				"english": orig_para,
				"korean": matched_trans,
				"status": "⚠️ 불일치",
				"similarity": round(best_similarity, 3),
				"suggestion": improved
			})
			translated_used.add(best_match_idx)
		else:
			# 미번역
			results.append({
				"english": orig_para,
				"korean": None,
				"status": "❌ 미번역",
				"similarity": 0.0,
				"suggestion": None
			})
	
	# 번역에는 있지만 원문에 없는 문단 (추가 번역)
	for trans_idx, trans_para in enumerate(translated_paras):
		if trans_idx not in translated_used:
			results.append({
				"english": None,
				"korean": trans_para,
				"status": "⚠️ 추가 번역",
				"similarity": 0.0,
				"suggestion": None
			})
	
	# 요약 계산
	total = len(results)
	ok_count = sum(1 for r in results if r["status"] == "ok")
	warning_count = sum(1 for r in results if "⚠️" in r["status"])
	missing_count = sum(1 for r in results if r["status"] == "❌ 미번역")
	accuracy = (ok_count / total * 100) if total > 0 else 0.0
	
	return {
		"results": results,
		"summary": {
			"total_paragraphs": total,
			"ok_count": ok_count,
			"warning_count": warning_count,
			"missing_count": missing_count,
			"accuracy_percent": round(accuracy, 2)
		}
	}


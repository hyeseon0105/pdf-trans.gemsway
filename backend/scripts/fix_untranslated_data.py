"""
번역되지 않은 데이터 수정 스크립트

translated_text에 영어가 들어가 있는 경우, 다시 번역하여 업데이트합니다.
"""

import sys
import os
from pathlib import Path
import re

# backend/app 모듈 import를 위한 경로 추가
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

try:
    from app.database import execute_query, init_connection_pool
    from app.services.translate_service import translate_text
except ImportError as e:
    print(f"[ERROR] 모듈을 찾을 수 없습니다: {e}")
    print("       backend/scripts/ 디렉토리에서 실행하거나")
    print("       PYTHONPATH를 설정하세요.")
    sys.exit(1)


def is_english_text(text: str) -> bool:
    """
    텍스트가 주로 영어인지 확인합니다.
    한글이 거의 없고 영어가 대부분이면 True 반환
    """
    if not text or not text.strip():
        return False
    
    # 한글 유니코드 범위: \uAC00-\uD7A3
    korean_chars = len(re.findall(r'[\uAC00-\uD7A3]', text))
    total_chars = len([c for c in text if c.isalnum() or c.isspace()])
    
    if total_chars == 0:
        return False
    
    # 한글 비율이 10% 미만이면 영어로 간주
    korean_ratio = korean_chars / total_chars if total_chars > 0 else 0
    return korean_ratio < 0.1


def get_untranslated_data():
    """
    translated_text에 영어가 들어가 있는 데이터를 가져옵니다.
    """
    try:
        init_connection_pool()
        
        query = """
            SELECT id, original_text, translated_text, edited_text
            FROM translations
            WHERE translated_text IS NOT NULL
            AND translated_text != ''
            ORDER BY id DESC
        """
        
        results = execute_query(query, fetch_all=True)
        
        # 영어로 된 translated_text 찾기
        untranslated = []
        for row in results:
            translated = row.get("translated_text", "")
            if translated and is_english_text(translated):
                untranslated.append({
                    "id": row["id"],
                    "original_text": row.get("original_text", ""),
                    "translated_text": translated,
                    "edited_text": row.get("edited_text", "")
                })
        
        return untranslated
        
    except Exception as e:
        print(f"[ERROR] 데이터 조회 중 오류 발생: {e}")
        return []


def retranslate_and_update(record_id: int, original_text: str):
    """
    원문을 다시 번역하여 translated_text를 업데이트합니다.
    """
    try:
        print(f"\n[번역 중] ID {record_id}: {original_text[:50]}...")
        
        # 번역 수행
        translated = translate_text(original_text, target_lang="ko")
        
        if not translated or not translated.strip():
            print(f"  [실패] 번역 결과가 비어있습니다.")
            return False
        
        # 영어가 여전히 들어가 있는지 확인
        if is_english_text(translated):
            print(f"  [실패] 번역 결과가 여전히 영어입니다: {translated[:50]}...")
            return False
        
        # 데이터베이스 업데이트
        update_query = """
            UPDATE translations
            SET translated_text = %s,
                updated_at = NOW()
            WHERE id = %s
        """
        
        execute_query(update_query, (translated, record_id), commit=True)
        
        print(f"  [성공] 번역 완료: {translated[:50]}...")
        return True
        
    except Exception as e:
        print(f"  [오류] 번역 실패: {e}")
        return False


def main():
    """
    메인 실행 함수
    """
    print("=" * 60)
    print("번역되지 않은 데이터 수정 스크립트")
    print("=" * 60)
    
    # 환경 변수 확인
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_db = os.getenv("MYSQL_DATABASE", "cadwell_translate")
    
    print(f"\n연결 정보: {mysql_user}@{mysql_host}/{mysql_db}")
    
    if not os.getenv("MYSQL_PASSWORD"):
        print("\n[WARNING] MYSQL_PASSWORD 환경 변수가 설정되지 않았습니다.")
        print("   예시 (Windows PowerShell):")
        print('   $env:MYSQL_PASSWORD="111111"')
        print()
    
    # 1. 번역되지 않은 데이터 찾기
    print("\n[STEP 1] 번역되지 않은 데이터 검색 중...")
    untranslated = get_untranslated_data()
    
    if not untranslated:
        print("✅ 번역되지 않은 데이터가 없습니다!")
        return
    
    print(f"[WARNING] {len(untranslated)}개의 번역되지 않은 데이터를 찾았습니다.")
    
    # 2. 각 데이터 다시 번역
    print(f"\n[STEP 2] {len(untranslated)}개 데이터 다시 번역 중...")
    success_count = 0
    fail_count = 0
    
    for i, record in enumerate(untranslated, 1):
        print(f"\n[{i}/{len(untranslated)}] ID: {record['id']}")
        
        # edited_text가 있으면 그것을 사용, 없으면 original_text 사용
        text_to_translate = record.get("edited_text") or record.get("original_text", "")
        
        if not text_to_translate.strip():
            print(f"  [건너뜀] 번역할 텍스트가 없습니다.")
            fail_count += 1
            continue
        
        # 이미 edited_text가 한국어면 그것을 translated_text로 복사
        if record.get("edited_text") and not is_english_text(record["edited_text"]):
            print(f"  [복사] edited_text를 translated_text로 복사")
            update_query = """
                UPDATE translations
                SET translated_text = %s,
                    updated_at = NOW()
                WHERE id = %s
            """
            try:
                execute_query(update_query, (record["edited_text"], record["id"]), commit=True)
                print(f"  [성공] 복사 완료")
                success_count += 1
            except Exception as e:
                print(f"  [오류] 복사 실패: {e}")
                fail_count += 1
        else:
            # original_text를 번역
            if retranslate_and_update(record["id"], record["original_text"]):
                success_count += 1
            else:
                fail_count += 1
    
    # 3. 결과 출력
    print("\n" + "=" * 60)
    print("[완료]")
    print(f"  성공: {success_count}개")
    print(f"  실패: {fail_count}개")
    print("=" * 60)


if __name__ == "__main__":
    main()


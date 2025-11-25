"""
데이터베이스에 있는 번역 데이터 확인 스크립트
"""

import sys
import os
from pathlib import Path

# backend/app/database.py 모듈 import를 위한 경로 추가
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

try:
    from app.database import execute_query, init_connection_pool
except ImportError as e:
    print(f"[ERROR] database 모듈을 찾을 수 없습니다: {e}")
    sys.exit(1)


def check_data():
    """데이터베이스의 번역 데이터 통계 확인"""
    try:
        init_connection_pool()
        
        # 전체 데이터 수
        total_query = "SELECT COUNT(*) as count FROM translations"
        total_result = execute_query(total_query, fetch_one=True)
        total_count = total_result["count"] if total_result else 0
        
        # user_edited=1이고 edited_text가 있는 데이터
        edited_query = """
            SELECT COUNT(*) as count
            FROM translations
            WHERE user_edited = 1
            AND edited_text IS NOT NULL
            AND edited_text != ''
        """
        edited_result = execute_query(edited_query, fetch_one=True)
        edited_count = edited_result["count"] if edited_result else 0
        
        # translated_text가 한국어인 데이터
        korean_translated_query = """
            SELECT COUNT(*) as count
            FROM translations
            WHERE translated_text IS NOT NULL
            AND translated_text != ''
            AND translated_text REGEXP '[가-힣]'
            AND (edited_text IS NULL OR edited_text = '')
        """
        korean_result = execute_query(korean_translated_query, fetch_one=True)
        korean_count = korean_result["count"] if korean_result else 0
        
        # translated_text가 영어인 데이터
        english_translated_query = """
            SELECT COUNT(*) as count
            FROM translations
            WHERE translated_text IS NOT NULL
            AND translated_text != ''
            AND translated_text NOT REGEXP '[가-힣]'
        """
        english_result = execute_query(english_translated_query, fetch_one=True)
        english_count = english_result["count"] if english_result else 0
        
        # 사용 가능한 데이터 (edited_text 또는 한국어 translated_text)
        available_query = """
            SELECT COUNT(*) as count
            FROM translations
            WHERE (
                (user_edited = 1 AND edited_text IS NOT NULL AND edited_text != '')
                OR
                (translated_text IS NOT NULL 
                 AND translated_text != '' 
                 AND translated_text REGEXP '[가-힣]'
                 AND (edited_text IS NULL OR edited_text = ''))
            )
            AND original_text IS NOT NULL
            AND original_text != ''
        """
        available_result = execute_query(available_query, fetch_one=True)
        available_count = available_result["count"] if available_result else 0
        
        print("=" * 60)
        print("데이터베이스 번역 데이터 통계")
        print("=" * 60)
        print(f"\n전체 번역 데이터: {total_count}개")
        print(f"사용자 수정 데이터 (user_edited=1, edited_text 있음): {edited_count}개")
        print(f"한국어 번역 데이터 (translated_text 한국어, edited_text 없음): {korean_count}개")
        print(f"영어 번역 데이터 (translated_text 영어): {english_count}개")
        print(f"\n[사용 가능한 학습 데이터]: {available_count}개")
        
        if available_count < 10:
            print(f"\n[WARNING] 사용 가능한 데이터가 {available_count}개입니다.")
            print(f"   최소 10개 이상 필요합니다!")
            print(f"\n해결 방법:")
            if korean_count > 0:
                print(f"  1. translated_text를 edited_text로 복사 ({korean_count}개 가능)")
                print(f"     UPDATE translations")
                print(f"     SET edited_text = translated_text, user_edited = 1")
                print(f"     WHERE translated_text REGEXP '[가-힣]'")
                print(f"     AND (edited_text IS NULL OR edited_text = '');")
            print(f"  2. 더 많은 번역 데이터 추가")
        else:
            print(f"\n[OK] 사용 가능한 데이터가 충분합니다!")
        
        # 샘플 데이터 보기
        if available_count > 0:
            sample_query = """
                SELECT id, 
                       LEFT(original_text, 50) as original,
                       LEFT(COALESCE(edited_text, translated_text), 50) as translation,
                       user_edited
                FROM translations
                WHERE (
                    (user_edited = 1 AND edited_text IS NOT NULL AND edited_text != '')
                    OR
                    (translated_text IS NOT NULL 
                     AND translated_text != '' 
                     AND translated_text REGEXP '[가-힣]'
                     AND (edited_text IS NULL OR edited_text = ''))
                )
                AND original_text IS NOT NULL
                AND original_text != ''
                ORDER BY user_edited DESC, id DESC
                LIMIT 5
            """
            samples = execute_query(sample_query, fetch_all=True)
            if samples:
                print(f"\n[샘플 데이터 (최근 5개)]:")
                for i, sample in enumerate(samples, 1):
                    source = "edited_text" if sample["user_edited"] else "translated_text"
                    print(f"\n  {i}. ID: {sample['id']} (출처: {source})")
                    print(f"     원문: {sample['original']}...")
                    print(f"     번역: {sample['translation']}...")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"[ERROR] 데이터 확인 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 환경 변수 확인
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_db = os.getenv("MYSQL_DATABASE", "cadwell_translate")
    
    print(f"연결 정보: {mysql_user}@{mysql_host}/{mysql_db}\n")
    
    if not os.getenv("MYSQL_PASSWORD"):
        print("[WARNING] MYSQL_PASSWORD 환경 변수가 설정되지 않았습니다.")
        print("   예시: $env:MYSQL_PASSWORD=\"111111\"\n")
    
    check_data()


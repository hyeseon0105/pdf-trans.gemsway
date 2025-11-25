"""
MySQL 데이터베이스에서 OpenAI Fine-tuning JSONL 데이터 생성

사용자가 직접 수정한 번역 데이터(user_edited=true)를 MySQL에서 가져와
OpenAI Chat Fine-tuning 형식의 JSONL 파일로 변환합니다.

실행 방법:
    python backend/scripts/generate_jsonl_from_mysql.py
"""

import json
import sys
import os
from pathlib import Path
from typing import List, Dict

# backend/app/database.py 모듈 import를 위한 경로 추가
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent
project_root = backend_dir.parent
sys.path.insert(0, str(backend_dir))

try:
    from app.database import execute_query, init_connection_pool
except ImportError:
    print("[ERROR] database 모듈을 찾을 수 없습니다.")
    print("       backend/scripts/ 디렉토리에서 실행하거나")
    print("       PYTHONPATH를 설정하세요.")
    sys.exit(1)


# 시스템 프롬프트
SYSTEM_PROMPT = "Cadwell Korea 의료기기 브로셔 전문 번역가"

# JSONL 파일 저장 경로 (프로젝트 루트에 저장)
import os
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
OUTPUT_FILE = project_root / "training_data.jsonl"


def get_edited_translations_from_mysql(min_count: int = 30) -> List[Dict[str, str]]:
    """
    MySQL 데이터베이스에서 사용자가 수정한 번역 데이터를 가져옵니다.
    
    Args:
        min_count: 최소 학습 데이터 개수 (기본값: 30)
    
    Returns:
        [{"originalText": "...", "editedText": "..."}] 리스트
    """
    try:
        # MySQL 연결 초기화
        init_connection_pool()
        
        # 먼저 데이터 개수 확인
        count_query = """
            SELECT COUNT(*) as count
            FROM translations 
            WHERE (
                (user_edited = 1 AND edited_text IS NOT NULL AND edited_text != '')
                OR
                (translated_text IS NOT NULL 
                 AND translated_text != '' 
                 AND translated_text REGEXP '[가-힣]'  -- 한글이 있는 것만
                 AND (edited_text IS NULL OR edited_text = ''))
            )
            AND original_text IS NOT NULL
            AND original_text != ''
        """
        
        count_result = execute_query(count_query, fetch_all=True)
        total_count = count_result[0]["count"] if count_result else 0
        
        print(f"[INFO] 사용 가능한 학습 데이터: {total_count}개")
        
        if total_count < min_count:
            print(f"[SKIP] 학습 데이터가 {total_count}개로 최소 요구사항({min_count}개)보다 적습니다.")
            print(f"       데이터가 {min_count}개 이상 모일 때까지 대기하세요.")
            return []
        
        # user_edited=true이고 edited_text가 있는 레코드 조회
        # 또는 translated_text가 한국어인 경우도 포함
        query = """
            SELECT original_text, 
                   COALESCE(edited_text, translated_text) as edited_text,
                   user_edited,
                   id,
                   updated_at
            FROM translations 
            WHERE (
                (user_edited = 1 AND edited_text IS NOT NULL AND edited_text != '')
                OR
                (translated_text IS NOT NULL 
                 AND translated_text != '' 
                 AND translated_text REGEXP '[가-힣]'  -- 한글이 있는 것만
                 AND (edited_text IS NULL OR edited_text = ''))
            )
            AND original_text IS NOT NULL
            AND original_text != ''
            ORDER BY user_edited DESC, updated_at DESC, id DESC
            LIMIT 200  -- 최대 200개까지
        """
        
        results = execute_query(query, fetch_all=True)
        
        # 결과를 Dict 리스트로 변환
        translations = []
        for row in results:
            translations.append({
                "originalText": row["original_text"],
                "editedText": row["edited_text"],
                "id": row.get("id"),
                "updated_at": row.get("updated_at")
            })
        
        print(f"[OK] MySQL에서 {len(translations)}개의 사용자 수정 번역 데이터를 가져왔습니다.")
        print(f"     (최소 요구사항: {min_count}개, 현재: {len(translations)}개)")
        return translations
        
    except Exception as e:
        print(f"[ERROR] MySQL에서 데이터를 가져오는 중 오류 발생: {e}")
        return []


def convert_to_openai_format(data: List[Dict[str, str]]) -> List[Dict]:
    """
    OpenAI Fine-tuning Chat 형식으로 변환
    
    형식:
    {
        "messages": [
            {"role": "system", "content": "시스템 프롬프트"},
            {"role": "user", "content": "영문 원문"},
            {"role": "assistant", "content": "한국어 번역"}
        ]
    }
    """
    formatted_data = []
    
    for item in data:
        formatted_item = {
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": item["originalText"]
                },
                {
                    "role": "assistant",
                    "content": item["editedText"]
                }
            ]
        }
        formatted_data.append(formatted_item)
    
    return formatted_data


def save_to_jsonl(data: List[Dict], output_path):
    """
    데이터를 JSONL 파일로 저장
    각 줄은 하나의 JSON 객체
    """
    # Path 객체를 문자열로 변환
    if isinstance(output_path, Path):
        output_path = str(output_path)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in data:
            json_line = json.dumps(item, ensure_ascii=False)
            f.write(json_line + '\n')
    
    print(f"[OK] JSONL 파일이 생성되었습니다: {output_path}")
    print(f"   총 {len(data)}개의 학습 예제")


def validate_jsonl(file_path):
    """
    생성된 JSONL 파일의 유효성을 검사합니다.
    """
    # Path 객체를 문자열로 변환
    if isinstance(file_path, Path):
        file_path = str(file_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        print(f"\n[VALIDATE] JSONL 파일 검증:")
        print(f"   - 총 라인 수: {len(lines)}")
        
        for i, line in enumerate(lines[:3]):  # 처음 3개만 검증
            try:
                data = json.loads(line)
                assert "messages" in data
                assert len(data["messages"]) == 3
                assert data["messages"][0]["role"] == "system"
                assert data["messages"][1]["role"] == "user"
                assert data["messages"][2]["role"] == "assistant"
                
                if i == 0:
                    print(f"\n   [OK] 첫 번째 예제:")
                    print(f"      User: {data['messages'][1]['content'][:50]}...")
                    print(f"      Assistant: {data['messages'][2]['content'][:50]}...")
            except Exception as e:
                print(f"   [ERROR] 라인 {i+1} 오류: {e}")
                return False
        
        print(f"   [OK] JSONL 형식이 올바릅니다!")
        return True
        
    except Exception as e:
        print(f"[ERROR] 파일 검증 실패: {e}")
        return False


def main():
    """
    메인 실행 함수
    """
    print("=" * 60)
    print("MySQL → OpenAI Fine-tuning JSONL 데이터 생성기")
    print("=" * 60)
    
    # 1. MySQL에서 데이터 가져오기
    print("\n[STEP 1] MySQL에서 데이터 가져오기...")
    
    # 환경 변수 확인
    mysql_host = os.getenv("MYSQL_HOST", "localhost")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_db = os.getenv("MYSQL_DATABASE", "cadwell_translate")
    
    print(f"   연결 정보: {mysql_user}@{mysql_host}/{mysql_db}")
    
    if not os.getenv("MYSQL_PASSWORD"):
        print("\n[WARNING] MYSQL_PASSWORD 환경 변수가 설정되지 않았습니다.")
        print("   환경 변수를 설정하거나 .env 파일을 생성하세요.")
        print("\n   예시 (Windows PowerShell):")
        print('   $env:MYSQL_PASSWORD="your_password"')
        print("\n   예시 (Linux/Mac):")
        print('   export MYSQL_PASSWORD="your_password"')
        print()
    
    # 최소 학습 데이터 개수 (환경 변수로 설정 가능, 기본값: 20)
    min_training_count = int(os.getenv("MIN_TRAINING_COUNT", "30"))
    print(f"\n[INFO] 최소 학습 데이터 요구사항: {min_training_count}개")
    print(f"       데이터가 {min_training_count}개 이상 모였을 때만 학습합니다.")
    
    translations = get_edited_translations_from_mysql(min_count=min_training_count)
    
    if not translations:
        print("\n[ERROR] 데이터가 없습니다.")
        print("\n가능한 원인:")
        print("  1. MySQL 연결 실패 (비밀번호, 호스트, DB명 확인)")
        print("  2. translations 테이블이 없음 (schema_mysql.sql 실행 필요)")
        print("  3. user_edited=1인 데이터가 없음")
        print("\n해결 방법:")
        print("  - MYSQL_SETUP.md 가이드를 참고하세요")
        print("  - API를 사용하여 번역 데이터를 추가하세요")
        return
    
    # 2. OpenAI 형식으로 변환
    print(f"\n[STEP 2] OpenAI Fine-tuning 형식으로 변환 중...")
    formatted_data = convert_to_openai_format(translations)
    
    # 3. JSONL 파일로 저장
    print(f"\n[STEP 3] JSONL 파일 저장 중...")
    save_to_jsonl(formatted_data, OUTPUT_FILE)
    
    # 4. 유효성 검사
    print(f"\n[STEP 4] 파일 검증 중...")
    validate_jsonl(OUTPUT_FILE)
    
    # 완료
    print("\n" + "=" * 60)
    print("[SUCCESS] 완료!")
    print(f"   파일 위치: {OUTPUT_FILE}")
    print(f"   학습 예제: {len(formatted_data)}개")
    
    min_count = int(os.getenv("MIN_TRAINING_COUNT", "30"))
    
    if len(formatted_data) < min_count:
        print(f"\n[WARNING] 학습 예제가 {len(formatted_data)}개입니다.")
        print(f"   최소 {min_count}개 이상 필요합니다!")
        print(f"\n해결 방법:")
        print(f"  1. 데이터베이스에 더 많은 번역 데이터 추가")
        print(f"  2. 사용자가 번역을 수정하면 자동으로 학습 데이터에 추가됩니다")
        print(f"  3. 또는 MIN_TRAINING_COUNT 환경 변수를 낮춰서 조정 가능")
        print(f"\n[INFO] 주기적 업데이트 전략:")
        print(f"  - 데이터가 {min_count}개 이상 모였을 때만 학습")
        print(f"  - 비용 절감 및 더 나은 학습 품질")
    else:
        print(f"\n[OK] 학습 예제가 충분합니다 ({len(formatted_data)}개)")
        print(f"\n[INFO] 주기적 업데이트 전략:")
        print(f"  ✓ 데이터가 {min_count}개 이상 모였습니다")
        print(f"  ✓ 파인튜닝 모델 업데이트 준비 완료")
        print(f"\n다음 단계:")
        print(f"  1. training_data.jsonl을 Google Colab에 업로드")
        print(f"  2. openai_finetuning_complete.ipynb 노트북 실행")
        print(f"  3. Fine-tuned 모델 ID를 .env 파일에 추가")
        print(f"\n[팁] 다음 업데이트는 새로운 데이터가 {min_count}개 이상 모였을 때 진행하세요.")
    print("=" * 60)


if __name__ == "__main__":
    main()



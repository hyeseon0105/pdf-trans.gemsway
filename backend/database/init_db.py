"""
데이터베이스 초기화 스크립트

SQLite 데이터베이스를 생성하고 스키마와 샘플 데이터를 삽입합니다.

사용법:
    python backend/database/init_db.py
"""

import sqlite3
import os
from pathlib import Path

# 데이터베이스 파일 경로
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "translations.db"
SCHEMA_PATH = DB_DIR / "schema_sqlite.sql"


def create_database():
    """데이터베이스 생성 및 스키마 적용"""
    
    print("=" * 60)
    print("번역 데이터베이스 초기화")
    print("=" * 60)
    
    # 기존 DB가 있으면 백업
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix('.db.backup')
        print(f"\n[WARNING] 기존 데이터베이스를 백업합니다: {backup_path}")
        if backup_path.exists():
            backup_path.unlink()
        DB_PATH.rename(backup_path)
    
    # 새 DB 생성
    print(f"\n[DB] 데이터베이스 생성: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 스키마 파일 읽기
    print(f"[SCHEMA] 스키마 파일 읽기: {SCHEMA_PATH}")
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_sql = f.read()
    
    # SQL 문 실행
    try:
        cursor.executescript(schema_sql)
    except sqlite3.Error as e:
        print(f"[WARNING] SQL 실행 중 경고: {e}")
    
    conn.commit()
    
    # 결과 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print(f"\n[SUCCESS] 데이터베이스가 생성되었습니다!")
    print(f"\n[TABLES] 생성된 테이블:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
        count = cursor.fetchone()[0]
        print(f"   - {table[0]}: {count}개 레코드")
    
    # 샘플 데이터 확인
    cursor.execute("""
        SELECT COUNT(*) FROM translations WHERE userEdited = 1
    """)
    edited_count = cursor.fetchone()[0]
    
    print(f"\n[DATA] Fine-tuning 가능한 데이터: {edited_count}개")
    print(f"   (userEdited = true인 레코드)")
    
    # 샘플 데이터 미리보기
    cursor.execute("""
        SELECT originalText, editedText 
        FROM translations 
        WHERE userEdited = 1 
        LIMIT 3
    """)
    samples = cursor.fetchall()
    
    if samples:
        print(f"\n[PREVIEW] 샘플 데이터 미리보기:")
        for i, (orig, edited) in enumerate(samples, 1):
            print(f"\n   [{i}]")
            print(f"   원문: {orig[:60]}...")
            print(f"   번역: {edited[:60]}...")
    
    conn.close()
    
    print(f"\n" + "=" * 60)
    print("[SUCCESS] 초기화 완료!")
    print(f"\n데이터베이스 경로: {DB_PATH.absolute()}")
    print(f"\n다음 단계:")
    print(f"  1. 데이터베이스에 더 많은 번역 데이터 추가")
    print(f"  2. backend/scripts/generate_jsonl_for_finetuning.py 실행")
    print(f"  3. Google Colab에서 Fine-tuning 진행")
    print("=" * 60)


def add_sample_data():
    """추가 샘플 데이터 삽입 (선택사항)"""
    
    if not DB_PATH.exists():
        print("[ERROR] 데이터베이스가 없습니다. 먼저 create_database()를 실행하세요.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    additional_samples = [
        (
            "The integrated EMG/NCS system supports multiple test protocols.",
            "통합 EMG/NCS 시스템은 여러 테스트 프로토콜을 지원합니다.",
            "통합형 EMG/NCS 시스템은 다양한 검사 프로토콜을 지원합니다.",
            True,
            "file_004",
            "product_catalog.pdf",
            0.89,
            "approved"
        ),
        (
            "Data export functionality allows seamless integration with EMR systems.",
            "데이터 내보내기 기능을 통해 EMR 시스템과 원활하게 통합할 수 있습니다.",
            "데이터 내보내기 기능으로 EMR 시스템과의 완벽한 연동이 가능합니다.",
            True,
            "file_004",
            "product_catalog.pdf",
            0.91,
            "approved"
        ),
        (
            "Customizable reporting templates streamline clinical workflow.",
            "사용자 정의 가능한 보고서 템플릿으로 임상 워크플로우를 간소화합니다.",
            "맞춤형 보고서 템플릿으로 임상 업무 흐름을 효율화합니다.",
            True,
            "file_005",
            "workflow_guide.pdf",
            0.87,
            "approved"
        ),
    ]
    
    cursor.executemany("""
        INSERT INTO translations 
        (originalText, translatedText, editedText, userEdited, fileId, fileName, confidence, reviewStatus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, additional_samples)
    
    conn.commit()
    
    print(f"[SUCCESS] {len(additional_samples)}개의 샘플 데이터가 추가되었습니다.")
    
    cursor.execute("SELECT COUNT(*) FROM translations WHERE userEdited = 1")
    total = cursor.fetchone()[0]
    print(f"   총 Fine-tuning 가능한 데이터: {total}개")
    
    conn.close()


def query_examples():
    """유용한 쿼리 예시"""
    
    if not DB_PATH.exists():
        print("[ERROR] 데이터베이스가 없습니다.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n" + "=" * 60)
    print("유용한 쿼리 예시")
    print("=" * 60)
    
    # 1. Fine-tuning 데이터
    cursor.execute("""
        SELECT COUNT(*) FROM translations 
        WHERE userEdited = 1 AND editedText IS NOT NULL
    """)
    count = cursor.fetchone()[0]
    print(f"\n1. Fine-tuning 가능한 데이터: {count}개")
    
    # 2. 파일별 통계
    cursor.execute("""
        SELECT 
            fileName,
            COUNT(*) as total,
            SUM(CASE WHEN userEdited = 1 THEN 1 ELSE 0 END) as edited,
            ROUND(AVG(confidence), 2) as avg_conf
        FROM translations
        GROUP BY fileName
    """)
    
    print(f"\n2. 파일별 번역 통계:")
    for row in cursor.fetchall():
        print(f"   - {row[0]}: 전체 {row[1]}개, 수정 {row[2]}개, 신뢰도 {row[3]}")
    
    # 3. 검토 대기
    cursor.execute("""
        SELECT COUNT(*) FROM translations WHERE reviewStatus = 'pending'
    """)
    pending = cursor.fetchone()[0]
    print(f"\n3. 검토 대기 중: {pending}개")
    
    conn.close()


if __name__ == "__main__":
    # 데이터베이스 초기화
    create_database()
    
    # 추가 샘플 데이터 (선택사항)
    # add_sample_data()
    
    # 쿼리 예시
    query_examples()


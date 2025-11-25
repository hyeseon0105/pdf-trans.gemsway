"""
환경 변수 확인 스크립트

.env 파일이 제대로 로드되는지 확인합니다.
"""

import os
import sys
from pathlib import Path

# .env 파일 로드
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    print(f"[1] .env 파일 경로: {env_path}")
    print(f"[2] .env 파일 존재: {env_path.exists()}")
    
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[3] .env 파일 로드 완료")
    else:
        print(f"[3] .env 파일을 찾을 수 없습니다!")
        print(f"    프로젝트 루트에 .env 파일을 생성하세요.")
        
except ImportError:
    print("[ERROR] python-dotenv가 설치되지 않았습니다.")
    print("        pip install python-dotenv")
    sys.exit(1)

# 환경 변수 확인
print("\n" + "=" * 60)
print("MySQL 환경 변수 확인")
print("=" * 60)

mysql_host = os.getenv("MYSQL_HOST", "localhost")
mysql_port = os.getenv("MYSQL_PORT", "3306")
mysql_user = os.getenv("MYSQL_USER", "root")
mysql_password = os.getenv("MYSQL_PASSWORD", "")
mysql_database = os.getenv("MYSQL_DATABASE", "cadwell_translate")

print(f"\nMYSQL_HOST:     {mysql_host}")
print(f"MYSQL_PORT:     {mysql_port}")
print(f"MYSQL_USER:     {mysql_user}")
print(f"MYSQL_PASSWORD: {'설정됨 (' + str(len(mysql_password)) + '자)' if mysql_password else '[X] 설정 안됨'}")
print(f"MYSQL_DATABASE: {mysql_database}")

if not mysql_password:
    print("\n[WARNING] MYSQL_PASSWORD가 설정되지 않았습니다!")
    print("\n.env 파일에 다음과 같이 추가하세요:")
    print("MYSQL_PASSWORD=your_actual_password")
else:
    print("\n[OK] 모든 MySQL 환경 변수가 설정되었습니다!")

# MySQL 연결 테스트
print("\n" + "=" * 60)
print("MySQL 연결 테스트")
print("=" * 60)

try:
    import mysql.connector
    
    print("\n[1] mysql-connector-python: 설치됨")
    
    conn = mysql.connector.connect(
        host=mysql_host,
        port=int(mysql_port),
        user=mysql_user,
        password=mysql_password
    )
    
    print("[2] MySQL 서버 연결: 성공")
    
    cursor = conn.cursor()
    cursor.execute(f"USE {mysql_database}")
    cursor.execute("SELECT COUNT(*) FROM translations")
    count = cursor.fetchone()[0]
    
    print(f"[3] 데이터베이스 '{mysql_database}': 연결 성공")
    print(f"[4] translations 테이블: 존재함 (데이터 {count}개)")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 모든 테스트 통과!")
    print("=" * 60)
    print("\n백엔드 서버를 시작할 수 있습니다:")
    print("  cd backend")
    print("  uvicorn app.main:app --reload --port 8000")
    
except mysql.connector.Error as err:
    print(f"\n[ERROR] MySQL 연결 실패: {err}")
    print("\n가능한 원인:")
    print("  1. MySQL 서버가 실행되지 않음")
    print("  2. 비밀번호가 올바르지 않음")
    print("  3. 데이터베이스가 존재하지 않음")
    sys.exit(1)
    
except ImportError:
    print("\n[ERROR] mysql-connector-python이 설치되지 않았습니다.")
    print("        pip install mysql-connector-python")
    sys.exit(1)



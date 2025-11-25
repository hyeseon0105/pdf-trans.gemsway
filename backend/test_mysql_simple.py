"""
간단한 MySQL 연결 테스트
"""
import os
import sys
from pathlib import Path

# .env 로드
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)
    print(f"[OK] .env 파일 로드: {env_path}")
except:
    print("[WARNING] .env 파일 로드 실패")

# 환경 변수 확인
host = os.getenv("MYSQL_HOST", "localhost")
port = int(os.getenv("MYSQL_PORT", "3306"))
user = os.getenv("MYSQL_USER", "root")
password = os.getenv("MYSQL_PASSWORD", "")
database = os.getenv("MYSQL_DATABASE", "cadwell_translate")

print(f"\n[1] MySQL 설정 확인:")
print(f"   HOST: {host}")
print(f"   PORT: {port}")
print(f"   USER: {user}")
print(f"   PASSWORD: {'설정됨' if password else '[X] 설정 안됨'}")
print(f"   DATABASE: {database}")

# MySQL 연결 테스트
try:
    import mysql.connector
    
    print(f"\n[2] MySQL 연결 시도...")
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        connection_timeout=5  # 5초 타임아웃
    )
    print(f"[OK] MySQL 서버 연결 성공!")
    
    # 데이터베이스 선택
    cursor = conn.cursor()
    cursor.execute(f"USE {database}")
    print(f"[OK] 데이터베이스 '{database}' 선택 성공")
    
    # 테이블 확인
    cursor.execute("SHOW TABLES LIKE 'translations'")
    if cursor.fetchone():
        print(f"[OK] translations 테이블 존재")
    else:
        print(f"[ERROR] translations 테이블이 없습니다!")
    
    cursor.close()
    conn.close()
    
    print(f"\n[SUCCESS] 모든 테스트 통과!")
    
except mysql.connector.Error as err:
    print(f"\n[ERROR] MySQL 연결 실패:")
    print(f"   에러 코드: {err.errno}")
    print(f"   에러 메시지: {err.msg}")
    
    if err.errno == 2003:
        print(f"\n[원인 분석]")
        print(f"   - MySQL 서버가 실행되지 않았거나")
        print(f"   - 포트 {port}가 차단되었거나")
        print(f"   - 호스트 {host}에 접근할 수 없습니다.")
        print(f"\n[해결 방법]")
        print(f"   1. MySQL Workbench에서 서버 상태 확인")
        print(f"   2. Windows 서비스에서 MySQL80 시작")
        print(f"   3. 포트 확인: netstat -an | findstr 3306")
    
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] 예상치 못한 오류: {e}")
    sys.exit(1)



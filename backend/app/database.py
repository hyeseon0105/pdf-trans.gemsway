"""
MySQL 데이터베이스 연결 모듈

mysql-connector-python을 사용하여 MySQL 데이터베이스에 연결합니다.
컨넥션 풀을 사용하여 성능을 최적화합니다.
"""

import mysql.connector
from mysql.connector import pooling
from typing import Optional, Dict, Any
import os
import logging
from pathlib import Path

# .env 파일 로드 (python-dotenv 사용)
try:
    from dotenv import load_dotenv
    
    # 현재 파일 위치: backend/app/database.py
    # 프로젝트 루트: backend/../ (즉, gems/)
    # parents[2]: backend/app/ -> backend/ -> gems/
    env_path = Path(__file__).resolve().parents[2] / '.env'
    
    # .env 파일이 없으면 backend/.env도 시도
    if not env_path.exists():
        env_path = Path(__file__).resolve().parents[1] / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[database.py] .env 파일 로드 완료: {env_path}")
    else:
        print(f"[database.py] WARNING: .env 파일을 찾을 수 없습니다: {env_path}")
        
except ImportError:
    print("[database.py] WARNING: python-dotenv가 설치되지 않았습니다. 환경 변수를 수동으로 설정하세요.")
except Exception as e:
    print(f"[database.py] WARNING: .env 파일 로드 중 오류: {e}")


# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# MySQL 연결 설정
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),  # 환경 변수로 설정하세요
    "database": os.getenv("MYSQL_DATABASE", "cadwell_translate"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "use_unicode": True,
    "autocommit": False,  # 명시적 트랜잭션 관리
}

# 연결 설정 로깅 (비밀번호 제외)
password_status = "설정됨" if MYSQL_CONFIG["password"] else "설정 안됨"
print(f"[database.py] MySQL 연결 설정: {MYSQL_CONFIG['user']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']} (비밀번호: {password_status})")
logger.info(f"MySQL 연결 설정: {MYSQL_CONFIG['user']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")

# 컨넥션 풀 설정
CONNECTION_POOL_CONFIG = {
    "pool_name": "cadwell_pool",
    "pool_size": 5,  # 동시 연결 수
    "pool_reset_session": True,
}

# 전역 컨넥션 풀
_connection_pool: Optional[pooling.MySQLConnectionPool] = None


def init_connection_pool() -> pooling.MySQLConnectionPool:
    """
    MySQL 컨넥션 풀을 초기화합니다.
    
    Returns:
        MySQLConnectionPool: 초기화된 컨넥션 풀
        
    Raises:
        mysql.connector.Error: MySQL 연결 실패 시
    """
    global _connection_pool
    
    if _connection_pool is not None:
        logger.info("컨넥션 풀이 이미 초기화되어 있습니다.")
        return _connection_pool
    
    try:
        # 컨넥션 풀 생성
        _connection_pool = pooling.MySQLConnectionPool(
            **MYSQL_CONFIG,
            **CONNECTION_POOL_CONFIG
        )
        
        logger.info(
            f"MySQL 컨넥션 풀 초기화 완료: "
            f"{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']} "
            f"-> {MYSQL_CONFIG['database']}"
        )
        
        return _connection_pool
        
    except mysql.connector.Error as err:
        logger.error(f"MySQL 컨넥션 풀 초기화 실패: {err}")
        raise


def get_connection():
    """
    컨넥션 풀에서 데이터베이스 연결을 가져옵니다.
    
    사용 예시:
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM translations")
            results = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    
    Returns:
        mysql.connector.connection.MySQLConnection: 데이터베이스 연결
        
    Raises:
        mysql.connector.Error: 연결 실패 시
    """
    global _connection_pool
    
    # 컨넥션 풀이 없으면 초기화
    if _connection_pool is None:
        init_connection_pool()
    
    try:
        connection = _connection_pool.get_connection()
        return connection
        
    except mysql.connector.Error as err:
        logger.error(f"MySQL 연결 가져오기 실패: {err}")
        raise


def test_connection() -> bool:
    """
    데이터베이스 연결을 테스트합니다.
    
    Returns:
        bool: 연결 성공 시 True, 실패 시 False
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        logger.info("MySQL 연결 테스트 성공")
        return result[0] == 1
        
    except mysql.connector.Error as err:
        logger.error(f"MySQL 연결 테스트 실패: {err}")
        return False


def execute_query(
    query: str,
    params: Optional[tuple] = None,
    fetch_one: bool = False,
    fetch_all: bool = True,
    commit: bool = False
) -> Optional[Any]:
    """
    SQL 쿼리를 실행합니다.
    
    Args:
        query: 실행할 SQL 쿼리
        params: 쿼리 파라미터 (prepared statement용)
        fetch_one: 단일 결과만 가져올지 여부
        fetch_all: 모든 결과를 가져올지 여부
        commit: 트랜잭션을 커밋할지 여부 (INSERT/UPDATE/DELETE)
    
    Returns:
        Optional[Any]: 쿼리 결과 (fetch_one/fetch_all에 따라)
        
    Raises:
        mysql.connector.Error: 쿼리 실행 실패 시
    """
    conn = None
    cursor = None
    
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 쿼리 실행
        cursor.execute(query, params or ())
        
        # 결과 가져오기
        result = None
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        
        # 트랜잭션 커밋 (INSERT/UPDATE/DELETE)
        if commit:
            conn.commit()
            # INSERT의 경우 auto_increment ID 반환
            if cursor.lastrowid:
                result = cursor.lastrowid
        
        return result
        
    except mysql.connector.Error as err:
        # 에러 발생 시 롤백
        if conn:
            conn.rollback()
        logger.error(f"쿼리 실행 실패: {err}")
        logger.error(f"쿼리: {query}")
        logger.error(f"파라미터: {params}")
        raise
        
    finally:
        # 리소스 정리
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def close_connection_pool():
    """
    컨넥션 풀을 종료합니다.
    애플리케이션 종료 시 호출해야 합니다.
    """
    global _connection_pool
    
    if _connection_pool:
        # 모든 연결 종료는 자동으로 처리됨
        _connection_pool = None
        logger.info("MySQL 컨넥션 풀이 종료되었습니다.")


# 애플리케이션 시작 시 초기화
def init_database():
    """
    데이터베이스를 초기화합니다.
    FastAPI 시작 이벤트에서 호출됩니다.
    """
    try:
        init_connection_pool()
        
        # 연결 테스트
        if test_connection():
            logger.info("데이터베이스 초기화 완료")
        else:
            logger.warning("데이터베이스 연결 테스트 실패")
            
    except Exception as e:
        logger.error(f"데이터베이스 초기화 중 오류: {e}")
        raise


# 애플리케이션 종료 시 정리
def cleanup_database():
    """
    데이터베이스 리소스를 정리합니다.
    FastAPI 종료 이벤트에서 호출됩니다.
    """
    close_connection_pool()
    logger.info("데이터베이스 정리 완료")


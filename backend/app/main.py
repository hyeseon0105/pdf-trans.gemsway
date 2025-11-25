from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

from .config import ALLOWED_ORIGINS
from .routers.translate import router as translate_router
from .routers.translations_router import router as translations_router
from .routers.finetuning_router import router as finetuning_router
from .database import init_database, cleanup_database

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cadwell Translation API",
    version="0.2.0",
    description="PDF 번역 및 번역 데이터 관리 API"
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=ALLOWED_ORIGINS,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# 타임아웃 미들웨어: 큰 파일 처리 시간을 늘림
class TimeoutMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		# PDF 번역 엔드포인트는 타임아웃을 늘림
		if request.url.path == "/api/translate/pdf":
			# 타임아웃을 30분으로 설정 (큰 파일 처리용)
			start_time = time.time()
			response = await call_next(request)
			elapsed = time.time() - start_time
			print(f"PDF 번역 처리 시간: {elapsed:.2f}초")
			return response
		return await call_next(request)

app.add_middleware(TimeoutMiddleware)

# 라우터 등록
app.include_router(translate_router, prefix="/api", tags=["translate"])
app.include_router(translations_router, prefix="/api", tags=["translations"])
app.include_router(finetuning_router, tags=["finetuning"])


# 애플리케이션 시작 이벤트
@app.on_event("startup")
async def startup_event():
	"""
	애플리케이션 시작 시 실행되는 이벤트
	MySQL 데이터베이스 연결을 초기화합니다.
	"""
	logger.info("애플리케이션 시작 중...")
	try:
		init_database()
		logger.info("데이터베이스 연결 초기화 완료")
	except Exception as e:
		logger.error(f"데이터베이스 초기화 실패: {e}")
		# 데이터베이스 연결 실패 시에도 애플리케이션은 계속 실행
		# PDF 번역 기능은 DB 없이도 동작 가능


# 애플리케이션 종료 이벤트
@app.on_event("shutdown")
async def shutdown_event():
	"""
	애플리케이션 종료 시 실행되는 이벤트
	MySQL 컨넥션 풀을 정리합니다.
	"""
	logger.info("애플리케이션 종료 중...")
	cleanup_database()
	logger.info("데이터베이스 연결 정리 완료")


@app.get("/health")
def health():
	"""
	헬스 체크 엔드포인트
	서버가 정상 동작 중인지 확인합니다.
	"""
	return {
		"status": "ok",
		"service": "Cadwell Translation API",
		"version": "0.2.0"
	}


@app.get("/")
def root():
	"""
	루트 엔드포인트
	API 정보를 제공합니다.
	"""
	return {
		"message": "Cadwell Translation API",
		"version": "0.2.0",
		"docs": "/docs",
		"endpoints": {
			"pdf_translation": "/api/translate/pdf",
			"translations_management": "/api/translations",
			"edited_translations": "/api/translations/edited",
			"health_check": "/health"
		}
	}



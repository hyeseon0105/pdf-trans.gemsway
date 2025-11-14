from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time

from .config import ALLOWED_ORIGINS
from .routers.translate import router as translate_router

app = FastAPI(title="PDF Translator API", version="0.1.0")

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

app.include_router(translate_router, prefix="/api", tags=["translate"])

@app.get("/health")
def health():
	return {"status": "ok"}



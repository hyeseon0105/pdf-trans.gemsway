from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(translate_router, prefix="/api", tags=["translate"])

@app.get("/health")
def health():
	return {"status": "ok"}



"""
파인튜닝 관련 API 엔드포인트
"""
import os
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# 스크립트 경로 추가
script_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(script_dir.parent))

from ..database import execute_query, init_connection_pool
from ..services.translate_service import _get_openai_client

router = APIRouter(prefix="/api/finetuning", tags=["finetuning"])


class FinetuningStatusResponse(BaseModel):
    status: str
    message: str
    data_count: int
    min_count: int
    can_train: bool
    job_id: Optional[str] = None
    model_id: Optional[str] = None


class FinetuningStartResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    data_count: int
    min_count: int


def get_training_data_count() -> int:
    """학습 가능한 데이터 개수 확인"""
    try:
        init_connection_pool()
        query = """
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
        result = execute_query(query, fetch_all=True)
        return result[0]["count"] if result else 0
    except Exception as e:
        print(f"Error getting training data count: {e}")
        return 0


@router.get("/status", response_model=FinetuningStatusResponse)
async def get_finetuning_status():
    """파인튜닝 상태 확인"""
    min_count = int(os.getenv("MIN_TRAINING_COUNT", "30"))
    data_count = get_training_data_count()
    can_train = data_count >= min_count
    
    return FinetuningStatusResponse(
        status="ready" if can_train else "waiting",
        message=f"학습 데이터: {data_count}개 / 최소 요구사항: {min_count}개" + 
                (" (학습 가능)" if can_train else " (데이터 부족)"),
        data_count=data_count,
        min_count=min_count,
        can_train=can_train
    )


def generate_jsonl_file() -> Optional[Path]:
    """JSONL 파일 생성"""
    try:
        # 스크립트 디렉토리에서 모듈 import
        import importlib.util
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "generate_jsonl_from_mysql.py"
        spec = importlib.util.spec_from_file_location("generate_jsonl_from_mysql", script_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        get_edited_translations_from_mysql = module.get_edited_translations_from_mysql
        convert_to_openai_format = module.convert_to_openai_format
        save_to_jsonl = module.save_to_jsonl
        
        min_count = int(os.getenv("MIN_TRAINING_COUNT", "30"))
        translations = get_edited_translations_from_mysql(min_count=min_count)
        
        if not translations:
            return None
        
        formatted_data = convert_to_openai_format(translations)
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        output_file = project_root / "training_data.jsonl"
        save_to_jsonl(formatted_data, output_file)
        
        return output_file
    except Exception as e:
        print(f"Error generating JSONL: {e}")
        import traceback
        traceback.print_exc()
        return None


def upload_file_to_openai(file_path: Path) -> Optional[str]:
    """OpenAI Files API에 파일 업로드"""
    try:
        client = _get_openai_client()
        if client is None:
            return None
        
        with open(file_path, "rb") as f:
            file_obj = client.files.create(
                file=f,
                purpose="fine-tune"
            )
        return file_obj.id
    except Exception as e:
        print(f"Error uploading file to OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return None


def start_finetuning_job(file_id: str) -> Optional[Dict[str, Any]]:
    """파인튜닝 작업 시작"""
    try:
        client = _get_openai_client()
        if client is None:
            return None
        
        base_model = os.getenv("FINETUNING_BASE_MODEL", "gpt-3.5-turbo-0125")
        suffix = os.getenv("FINETUNING_SUFFIX", "cadwell-medical-ko")
        
        job = client.fine_tuning.jobs.create(
            training_file=file_id,
            model=base_model,
            hyperparameters={
                "n_epochs": int(os.getenv("FINETUNING_N_EPOCHS", "3")),
            },
            suffix=suffix
        )
        
        return {
            "job_id": job.id,
            "status": job.status,
            "model": job.model
        }
    except Exception as e:
        print(f"Error starting finetuning job: {e}")
        import traceback
        traceback.print_exc()
        return None


@router.post("/start", response_model=FinetuningStartResponse)
async def start_finetuning(background_tasks: BackgroundTasks):
    """파인튜닝 시작"""
    min_count = int(os.getenv("MIN_TRAINING_COUNT", "30"))
    data_count = get_training_data_count()
    
    if data_count < min_count:
        raise HTTPException(
            status_code=400,
            detail=f"학습 데이터가 부족합니다. 현재: {data_count}개 / 필요: {min_count}개 이상"
        )
    
    # 1. JSONL 파일 생성
    jsonl_file = generate_jsonl_file()
    if jsonl_file is None or not jsonl_file.exists():
        raise HTTPException(
            status_code=500,
            detail="JSONL 파일 생성 실패"
        )
    
    # 2. OpenAI에 파일 업로드
    file_id = upload_file_to_openai(jsonl_file)
    if file_id is None:
        raise HTTPException(
            status_code=500,
            detail="OpenAI 파일 업로드 실패"
        )
    
    # 3. 파인튜닝 작업 시작
    job_info = start_finetuning_job(file_id)
    if job_info is None:
        raise HTTPException(
            status_code=500,
            detail="파인튜닝 작업 시작 실패"
        )
    
    return FinetuningStartResponse(
        status="started",
        message=f"파인튜닝 작업이 시작되었습니다. 작업 ID: {job_info['job_id']}",
        job_id=job_info["job_id"],
        data_count=data_count,
        min_count=min_count
    )


@router.get("/job/{job_id}")
async def get_finetuning_job_status(job_id: str):
    """파인튜닝 작업 상태 확인"""
    try:
        client = _get_openai_client()
        if client is None:
            raise HTTPException(status_code=500, detail="OpenAI 클라이언트 초기화 실패")
        
        job = client.fine_tuning.jobs.retrieve(job_id)
        
        result = {
            "job_id": job.id,
            "status": job.status,
            "model": job.model,
            "fine_tuned_model": job.fine_tuned_model,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
            "trained_tokens": job.trained_tokens,
            "error": job.error if hasattr(job, 'error') else None
        }
        
        # 학습이 완료되었고 모델 ID가 있으면 메시지에 포함
        if job.status == "succeeded" and job.fine_tuned_model:
            result["message"] = f"✅ 학습 완료! 모델 ID: {job.fine_tuned_model}\n\n이 모델은 '학습하기' 버튼을 눌렀을 때만 사용됩니다.\n일반 번역은 항상 gpt-4o-mini를 사용합니다."
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업 상태 확인 실패: {str(e)}")



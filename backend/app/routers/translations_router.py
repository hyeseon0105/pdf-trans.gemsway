"""
번역 데이터 관리 API 라우터

translations 테이블에 대한 CRUD 작업을 제공합니다.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import mysql.connector

from ..database import execute_query

# 라우터 생성
router = APIRouter(
    prefix="/translations",
    tags=["translations"],
    responses={404: {"description": "Not found"}},
)


# Pydantic 모델 정의

class TranslationCreate(BaseModel):
    """번역 데이터 생성 요청 모델"""
    # max_length 제한 제거: MySQL MEDIUMTEXT는 최대 16MB까지 저장 가능
    original_text: str = Field(..., description="영어 원문", min_length=1)
    translated_text: Optional[str] = Field(None, description="자동 번역 텍스트")
    edited_text: Optional[str] = Field(None, description="사용자가 수정한 번역 텍스트")
    user_edited: bool = Field(False, description="사용자가 수정했는지 여부")
    file_name: Optional[str] = Field(None, description="원본 파일명", max_length=255)
    confidence: Optional[float] = Field(None, description="번역 신뢰도 (0.0 ~ 1.0)", ge=0.0, le=1.0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "original_text": "Cadwell's EMG solutions are designed for comprehensive neuromuscular diagnostics.",
                "translated_text": "Cadwell의 EMG 솔루션은 포괄적인 신경근 진단을 위해 설계되었습니다.",
                "edited_text": "Cadwell의 EMG 솔루션은 포괄적인 신경근육 진단을 위해 설계되었습니다.",
                "user_edited": True,
                "file_name": "cadwell_brochure_2024.pdf",
                "confidence": 0.95
            }
        }


class TranslationResponse(BaseModel):
    """번역 데이터 응답 모델"""
    id: int
    original_text: str
    translated_text: Optional[str]
    edited_text: Optional[str]
    user_edited: bool
    file_name: Optional[str]
    confidence: Optional[float]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TranslationUpdate(BaseModel):
    """번역 데이터 수정 요청 모델"""
    # max_length 제한 제거: MySQL MEDIUMTEXT는 최대 16MB까지 저장 가능
    translated_text: Optional[str] = None
    edited_text: Optional[str] = None
    user_edited: Optional[bool] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


# API 엔드포인트

@router.post(
    "/",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="번역 데이터 생성",
    description="새로운 번역 데이터를 데이터베이스에 저장합니다."
)
async def create_translation(translation: TranslationCreate):
    """
    번역 데이터를 생성합니다.
    
    - **original_text**: 영어 원문 (필수)
    - **translated_text**: 자동 번역 텍스트 (선택)
    - **edited_text**: 사용자가 수정한 번역 텍스트 (선택)
    - **user_edited**: 사용자가 수정했는지 여부 (기본값: False)
    - **file_name**: 원본 파일명 (선택)
    - **confidence**: 번역 신뢰도 0.0~1.0 (선택)
    """
    try:
        # INSERT 쿼리
        query = """
            INSERT INTO translations 
            (original_text, translated_text, edited_text, user_edited, file_name, confidence, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """
        
        params = (
            translation.original_text,
            translation.translated_text,
            translation.edited_text,
            translation.user_edited,
            translation.file_name,
            translation.confidence,
        )
        
        # 쿼리 실행 및 생성된 ID 반환
        translation_id = execute_query(query, params, commit=True, fetch_all=False)
        
        return {
            "id": translation_id,
            "message": "번역 데이터가 성공적으로 생성되었습니다.",
            "original_text": translation.original_text,
            "user_edited": translation.user_edited
        }
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.get(
    "/",
    response_model=List[TranslationResponse],
    summary="모든 번역 데이터 조회",
    description="translations 테이블의 모든 데이터를 조회합니다."
)
async def get_all_translations(
    limit: int = 100,
    offset: int = 0,
    file_name: Optional[str] = None
):
    """
    모든 번역 데이터를 조회합니다.
    
    - **limit**: 가져올 최대 개수 (기본값: 100)
    - **offset**: 건너뛸 개수 (페이지네이션용, 기본값: 0)
    - **file_name**: 파일명으로 필터링 (선택)
    
    Returns:
        List[TranslationResponse]: 번역 데이터 리스트
    """
    try:
        # 기본 쿼리
        query = """
            SELECT 
                id, original_text, translated_text, edited_text, 
                user_edited, file_name, confidence, created_at, updated_at
            FROM translations
        """
        
        params = []
        
        # 파일명 필터링
        if file_name:
            query += " WHERE file_name = %s"
            params.append(file_name)
        
        # 정렬 및 페이지네이션
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        # 쿼리 실행
        results = execute_query(query, tuple(params), fetch_all=True)
        
        if not results:
            return []
        
        return results
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.get(
    "/edited",
    response_model=List[TranslationResponse],
    summary="사용자가 수정한 번역 데이터 조회",
    description="user_edited = 1 인 번역 데이터만 조회합니다. Fine-tuning 학습 데이터로 사용됩니다."
)
async def get_edited_translations(
    limit: int = 100,
    offset: int = 0
):
    """
    사용자가 수정한 번역 데이터만 조회합니다.
    
    user_edited = 1 이고 edited_text가 있는 데이터를 반환합니다.
    이 데이터는 OpenAI Fine-tuning 학습에 사용됩니다.
    
    - **limit**: 가져올 최대 개수 (기본값: 100)
    - **offset**: 건너뛸 개수 (페이지네이션용, 기본값: 0)
    
    Returns:
        List[TranslationResponse]: 사용자가 수정한 번역 데이터 리스트
    """
    try:
        query = """
            SELECT 
                id, original_text, translated_text, edited_text, 
                user_edited, file_name, confidence, created_at, updated_at
            FROM translations
            WHERE user_edited = 1 
            AND edited_text IS NOT NULL
            AND edited_text != ''
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        
        params = (limit, offset)
        
        # 쿼리 실행
        results = execute_query(query, params, fetch_all=True)
        
        if not results:
            return []
        
        return results
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.get(
    "/edited/count",
    summary="Fine-tuning 가능한 데이터 개수 조회",
    description="user_edited = 1 인 데이터의 총 개수를 반환합니다."
)
async def get_edited_count():
    """
    Fine-tuning 학습에 사용할 수 있는 데이터 개수를 반환합니다.
    
    Returns:
        dict: {"count": 개수, "message": "메시지"}
    """
    try:
        query = """
            SELECT COUNT(*) as count
            FROM translations
            WHERE user_edited = 1 
            AND edited_text IS NOT NULL
            AND edited_text != ''
        """
        
        result = execute_query(query, fetch_one=True)
        count = result["count"] if result else 0
        
        return {
            "count": count,
            "message": f"Fine-tuning 가능한 데이터: {count}개",
            "recommendation": "최소 50-100개, 권장 200개 이상" if count < 200 else "충분한 학습 데이터"
        }
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.get(
    "/{translation_id}",
    response_model=TranslationResponse,
    summary="번역 데이터 단일 조회",
    description="ID로 특정 번역 데이터를 조회합니다."
)
async def get_translation(translation_id: int):
    """
    ID로 특정 번역 데이터를 조회합니다.
    
    - **translation_id**: 번역 데이터 ID
    
    Returns:
        TranslationResponse: 번역 데이터
    """
    try:
        query = """
            SELECT 
                id, original_text, translated_text, edited_text, 
                user_edited, file_name, confidence, created_at, updated_at
            FROM translations
            WHERE id = %s
        """
        
        result = execute_query(query, (translation_id,), fetch_one=True)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ID {translation_id}인 번역 데이터를 찾을 수 없습니다."
            )
        
        return result
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.put(
    "/{translation_id}",
    response_model=dict,
    summary="번역 데이터 수정",
    description="기존 번역 데이터를 수정합니다. (사용자가 번역을 수정할 때 사용)"
)
async def update_translation(translation_id: int, update_data: TranslationUpdate):
    """
    번역 데이터를 수정합니다.
    
    주로 사용자가 자동 번역을 수정할 때 사용됩니다.
    수정된 데이터는 Fine-tuning 학습에 활용됩니다.
    
    - **translation_id**: 번역 데이터 ID
    - **update_data**: 수정할 데이터
    
    Returns:
        dict: 수정 결과 메시지
    """
    try:
        # 먼저 데이터가 존재하는지 확인
        check_query = "SELECT id FROM translations WHERE id = %s"
        existing = execute_query(check_query, (translation_id,), fetch_one=True)
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ID {translation_id}인 번역 데이터를 찾을 수 없습니다."
            )
        
        # 수정할 필드 구성
        update_fields = []
        params = []
        
        if update_data.translated_text is not None:
            update_fields.append("translated_text = %s")
            params.append(update_data.translated_text)
        
        if update_data.edited_text is not None:
            update_fields.append("edited_text = %s")
            params.append(update_data.edited_text)
        
        if update_data.user_edited is not None:
            update_fields.append("user_edited = %s")
            params.append(update_data.user_edited)
        
        if update_data.confidence is not None:
            update_fields.append("confidence = %s")
            params.append(update_data.confidence)
        
        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="수정할 데이터가 없습니다."
            )
        
        # updated_at 자동 갱신
        update_fields.append("updated_at = NOW()")
        
        # UPDATE 쿼리 실행
        query = f"""
            UPDATE translations 
            SET {', '.join(update_fields)}
            WHERE id = %s
        """
        params.append(translation_id)
        
        execute_query(query, tuple(params), commit=True, fetch_all=False)
        
        return {
            "id": translation_id,
            "message": "번역 데이터가 성공적으로 수정되었습니다.",
            "updated_fields": len(update_fields) - 1  # updated_at 제외
        }
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


@router.delete(
    "/{translation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="번역 데이터 삭제",
    description="번역 데이터를 삭제합니다."
)
async def delete_translation(translation_id: int):
    """
    번역 데이터를 삭제합니다.
    
    - **translation_id**: 번역 데이터 ID
    """
    try:
        # 먼저 데이터가 존재하는지 확인
        check_query = "SELECT id FROM translations WHERE id = %s"
        existing = execute_query(check_query, (translation_id,), fetch_one=True)
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ID {translation_id}인 번역 데이터를 찾을 수 없습니다."
            )
        
        # DELETE 쿼리 실행
        query = "DELETE FROM translations WHERE id = %s"
        execute_query(query, (translation_id,), commit=True, fetch_all=False)
        
        return None
        
    except mysql.connector.Error as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 오류: {str(err)}"
        )


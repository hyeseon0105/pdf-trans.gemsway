-- 번역 데이터베이스 스키마
-- SQLite, PostgreSQL, MySQL 모두 호환 가능

-- 번역 테이블
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- PostgreSQL: SERIAL PRIMARY KEY
    
    -- 원문 및 번역
    originalText TEXT NOT NULL,            -- 영어 원문
    translatedText TEXT,                   -- 자동 번역된 텍스트
    editedText TEXT,                       -- 사용자가 수정한 최종 번역 텍스트
    
    -- 메타데이터
    userEdited BOOLEAN DEFAULT FALSE,      -- 사용자가 수정했는지 여부
    fileId VARCHAR(255),                   -- 원본 PDF 파일 ID
    fileName VARCHAR(255),                 -- 원본 파일명
    pageNumber INTEGER,                    -- PDF 페이지 번호
    
    -- 번역 품질 정보
    confidence FLOAT,                      -- 번역 신뢰도 (0.0 ~ 1.0)
    reviewStatus VARCHAR(50),              -- 'pending', 'approved', 'rejected'
    
    -- 타임스탬프
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 인덱스
    INDEX idx_userEdited (userEdited),
    INDEX idx_fileId (fileId),
    INDEX idx_reviewStatus (reviewStatus)
);

-- 파일 정보 테이블 (선택사항)
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- PostgreSQL: SERIAL PRIMARY KEY
    fileId VARCHAR(255) UNIQUE NOT NULL,
    fileName VARCHAR(255) NOT NULL,
    fileSize INTEGER,
    uploadedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processedAt TIMESTAMP,
    status VARCHAR(50) DEFAULT 'uploaded'  -- 'uploaded', 'processing', 'completed', 'failed'
);

-- 사용자 테이블 (선택사항)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'editor',     -- 'editor', 'reviewer', 'admin'
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 번역 히스토리 테이블 (선택사항 - 수정 이력 추적)
CREATE TABLE IF NOT EXISTS translation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    translationId INTEGER NOT NULL,
    previousText TEXT,
    newText TEXT,
    editedBy VARCHAR(255),
    editedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (translationId) REFERENCES translations(id)
);


-- ===================================================================
-- PostgreSQL 전용 구문 (SQLite에서는 주석 처리)
-- ===================================================================

-- PostgreSQL용 스키마 (위 내용을 PostgreSQL 문법으로 변환)
/*
-- 자동 업데이트 트리거 함수
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updatedAt = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- translations 테이블에 트리거 적용
CREATE TRIGGER update_translations_updated_at 
    BEFORE UPDATE ON translations
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
*/


-- ===================================================================
-- 샘플 데이터 삽입
-- ===================================================================

-- 샘플 번역 데이터 (userEdited = true)
INSERT INTO translations (originalText, translatedText, editedText, userEdited, fileId, fileName, confidence, reviewStatus)
VALUES
    (
        'Cadwell''s EMG solutions are designed for comprehensive neuromuscular diagnostics.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근 진단을 위해 설계되었습니다.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근육 진단을 위해 설계되었습니다.',
        TRUE,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.95,
        'approved'
    ),
    (
        'Our devices provide accurate and reliable measurements for clinical assessments.',
        '우리 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        '당사의 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        TRUE,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.92,
        'approved'
    ),
    (
        'The system integrates seamlessly with existing hospital infrastructure.',
        '시스템은 기존 병원 인프라와 원활하게 통합됩니다.',
        '이 시스템은 기존 병원 인프라와 완벽하게 통합됩니다.',
        TRUE,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.88,
        'approved'
    ),
    (
        'Advanced filtering algorithms ensure high-quality signal acquisition.',
        '고급 필터링 알고리즘은 고품질 신호 획득을 보장합니다.',
        '고급 필터링 알고리즘으로 고품질 신호 획득을 보장합니다.',
        TRUE,
        'file_002',
        'technical_specs.pdf',
        0.90,
        'approved'
    ),
    (
        'The user interface is designed for efficiency and ease of use.',
        '사용자 인터페이스는 효율성과 사용 용이성을 위해 설계되었습니다.',
        '사용자 인터페이스는 효율성과 사용 편의성을 위해 설계되었습니다.',
        TRUE,
        'file_002',
        'technical_specs.pdf',
        0.93,
        'approved'
    ),
    (
        'Real-time monitoring capabilities enable immediate clinical decision-making.',
        '실시간 모니터링 기능은 즉각적인 임상 의사 결정을 가능하게 합니다.',
        '실시간 모니터링 기능으로 즉각적인 임상 의사 결정이 가능합니다.',
        TRUE,
        'file_003',
        'user_manual.pdf',
        0.91,
        'approved'
    );

-- 샘플 번역 데이터 (userEdited = false - 자동 번역만 있는 경우)
INSERT INTO translations (originalText, translatedText, editedText, userEdited, fileId, fileName, confidence, reviewStatus)
VALUES
    (
        'Contact our support team for technical assistance.',
        '기술 지원을 위해 지원팀에 문의하십시오.',
        NULL,
        FALSE,
        'file_003',
        'user_manual.pdf',
        0.85,
        'pending'
    ),
    (
        'Product warranty is valid for 2 years from date of purchase.',
        '제품 보증은 구매일로부터 2년 동안 유효합니다.',
        NULL,
        FALSE,
        'file_003',
        'user_manual.pdf',
        0.87,
        'pending'
    );


-- ===================================================================
-- 유용한 쿼리 예시
-- ===================================================================

-- 1. Fine-tuning용 데이터 추출 (userEdited=true)
-- SELECT originalText, editedText 
-- FROM translations 
-- WHERE userEdited = TRUE 
-- AND editedText IS NOT NULL
-- ORDER BY id DESC;

-- 2. 파일별 번역 통계
-- SELECT 
--     fileName,
--     COUNT(*) as total_translations,
--     SUM(CASE WHEN userEdited = TRUE THEN 1 ELSE 0 END) as edited_count,
--     AVG(confidence) as avg_confidence
-- FROM translations
-- GROUP BY fileName;

-- 3. 검토 대기 중인 번역
-- SELECT * FROM translations
-- WHERE reviewStatus = 'pending'
-- ORDER BY createdAt DESC;

-- 4. 최근 수정된 번역
-- SELECT * FROM translations
-- WHERE userEdited = TRUE
-- ORDER BY updatedAt DESC
-- LIMIT 10;




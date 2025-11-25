-- SQLite 전용 번역 데이터베이스 스키마

-- 번역 테이블
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- 원문 및 번역
    originalText TEXT NOT NULL,
    translatedText TEXT,
    editedText TEXT,
    
    -- 메타데이터
    userEdited BOOLEAN DEFAULT 0,
    fileId VARCHAR(255),
    fileName VARCHAR(255),
    pageNumber INTEGER,
    
    -- 번역 품질 정보
    confidence REAL,
    reviewStatus VARCHAR(50),
    
    -- 타임스탬프
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_userEdited ON translations(userEdited);
CREATE INDEX IF NOT EXISTS idx_fileId ON translations(fileId);
CREATE INDEX IF NOT EXISTS idx_reviewStatus ON translations(reviewStatus);

-- 파일 정보 테이블 (선택사항)
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fileId VARCHAR(255) UNIQUE NOT NULL,
    fileName VARCHAR(255) NOT NULL,
    fileSize INTEGER,
    uploadedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processedAt TIMESTAMP,
    status VARCHAR(50) DEFAULT 'uploaded'
);

-- 샘플 데이터 삽입
INSERT INTO translations (originalText, translatedText, editedText, userEdited, fileId, fileName, confidence, reviewStatus)
VALUES
    (
        'Cadwell''s EMG solutions are designed for comprehensive neuromuscular diagnostics.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근 진단을 위해 설계되었습니다.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근육 진단을 위해 설계되었습니다.',
        1,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.95,
        'approved'
    ),
    (
        'Our devices provide accurate and reliable measurements for clinical assessments.',
        '우리 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        '당사의 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        1,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.92,
        'approved'
    ),
    (
        'The system integrates seamlessly with existing hospital infrastructure.',
        '시스템은 기존 병원 인프라와 원활하게 통합됩니다.',
        '이 시스템은 기존 병원 인프라와 완벽하게 통합됩니다.',
        1,
        'file_001',
        'cadwell_brochure_2024.pdf',
        0.88,
        'approved'
    ),
    (
        'Advanced filtering algorithms ensure high-quality signal acquisition.',
        '고급 필터링 알고리즘은 고품질 신호 획득을 보장합니다.',
        '고급 필터링 알고리즘으로 고품질 신호 획득을 보장합니다.',
        1,
        'file_002',
        'technical_specs.pdf',
        0.90,
        'approved'
    ),
    (
        'The user interface is designed for efficiency and ease of use.',
        '사용자 인터페이스는 효율성과 사용 용이성을 위해 설계되었습니다.',
        '사용자 인터페이스는 효율성과 사용 편의성을 위해 설계되었습니다.',
        1,
        'file_002',
        'technical_specs.pdf',
        0.93,
        'approved'
    ),
    (
        'Real-time monitoring capabilities enable immediate clinical decision-making.',
        '실시간 모니터링 기능은 즉각적인 임상 의사 결정을 가능하게 합니다.',
        '실시간 모니터링 기능으로 즉각적인 임상 의사 결정이 가능합니다.',
        1,
        'file_003',
        'user_manual.pdf',
        0.91,
        'approved'
    ),
    (
        'Contact our support team for technical assistance.',
        '기술 지원을 위해 지원팀에 문의하십시오.',
        NULL,
        0,
        'file_003',
        'user_manual.pdf',
        0.85,
        'pending'
    ),
    (
        'Product warranty is valid for 2 years from date of purchase.',
        '제품 보증은 구매일로부터 2년 동안 유효합니다.',
        NULL,
        0,
        'file_003',
        'user_manual.pdf',
        0.87,
        'pending'
    );



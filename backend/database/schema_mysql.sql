-- MySQL 데이터베이스 및 테이블 스키마
-- Cadwell Translation Service

-- 데이터베이스 생성 (존재하지 않을 경우)
CREATE DATABASE IF NOT EXISTS cadwell_translate
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 데이터베이스 선택
USE cadwell_translate;

-- translations 테이블 생성
CREATE TABLE IF NOT EXISTS translations (
    -- 기본 키
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- 번역 데이터 (MEDIUMTEXT: 최대 16MB까지 저장 가능)
    original_text MEDIUMTEXT NOT NULL COMMENT '영어 원문',
    translated_text MEDIUMTEXT COMMENT '자동 번역 텍스트',
    edited_text MEDIUMTEXT COMMENT '사용자가 수정한 최종 번역 텍스트',
    
    -- 메타데이터
    user_edited BOOLEAN DEFAULT FALSE COMMENT '사용자가 수정했는지 여부',
    file_name VARCHAR(255) COMMENT '원본 파일명',
    page_number INT COMMENT 'PDF 페이지 번호',
    
    -- 품질 정보
    confidence DECIMAL(3, 2) COMMENT '번역 신뢰도 (0.00 ~ 1.00)',
    review_status VARCHAR(50) DEFAULT 'pending' COMMENT '검토 상태: pending, approved, rejected',
    
    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시간',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시간',
    
    -- 인덱스
    INDEX idx_user_edited (user_edited),
    INDEX idx_file_name (file_name),
    INDEX idx_review_status (review_status),
    INDEX idx_created_at (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='번역 데이터 저장 테이블';


-- files 테이블 (선택사항 - 파일 정보 관리)
CREATE TABLE IF NOT EXISTS files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_id VARCHAR(255) UNIQUE NOT NULL COMMENT '파일 고유 ID',
    file_name VARCHAR(255) NOT NULL COMMENT '파일명',
    file_size INT COMMENT '파일 크기 (bytes)',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '업로드 시간',
    processed_at TIMESTAMP NULL COMMENT '처리 완료 시간',
    status VARCHAR(50) DEFAULT 'uploaded' COMMENT '파일 상태: uploaded, processing, completed, failed',
    
    INDEX idx_file_id (file_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='업로드된 파일 정보';


-- users 테이블 (선택사항 - 사용자 관리)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL COMMENT '이메일',
    name VARCHAR(255) COMMENT '사용자 이름',
    role VARCHAR(50) DEFAULT 'editor' COMMENT '권한: editor, reviewer, admin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '가입 시간',
    
    INDEX idx_email (email),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사용자 정보';


-- translation_history 테이블 (선택사항 - 수정 이력 추적)
CREATE TABLE IF NOT EXISTS translation_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    translation_id INT NOT NULL COMMENT '번역 데이터 ID',
    previous_text TEXT COMMENT '이전 텍스트',
    new_text TEXT COMMENT '새 텍스트',
    edited_by VARCHAR(255) COMMENT '수정한 사용자',
    edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '수정 시간',
    
    FOREIGN KEY (translation_id) REFERENCES translations(id) ON DELETE CASCADE,
    INDEX idx_translation_id (translation_id),
    INDEX idx_edited_at (edited_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='번역 수정 이력';


-- ===================================================================
-- 샘플 데이터 삽입
-- ===================================================================

-- 샘플 번역 데이터 (user_edited = 1)
INSERT INTO translations (original_text, translated_text, edited_text, user_edited, file_name, confidence, review_status)
VALUES
    (
        'Cadwell\'s EMG solutions are designed for comprehensive neuromuscular diagnostics.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근 진단을 위해 설계되었습니다.',
        'Cadwell의 EMG 솔루션은 포괄적인 신경근육 진단을 위해 설계되었습니다.',
        TRUE,
        'cadwell_brochure_2024.pdf',
        0.95,
        'approved'
    ),
    (
        'Our devices provide accurate and reliable measurements for clinical assessments.',
        '우리 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        '당사의 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.',
        TRUE,
        'cadwell_brochure_2024.pdf',
        0.92,
        'approved'
    ),
    (
        'The system integrates seamlessly with existing hospital infrastructure.',
        '시스템은 기존 병원 인프라와 원활하게 통합됩니다.',
        '이 시스템은 기존 병원 인프라와 완벽하게 통합됩니다.',
        TRUE,
        'cadwell_brochure_2024.pdf',
        0.88,
        'approved'
    ),
    (
        'Advanced filtering algorithms ensure high-quality signal acquisition.',
        '고급 필터링 알고리즘은 고품질 신호 획득을 보장합니다.',
        '고급 필터링 알고리즘으로 고품질 신호 획득을 보장합니다.',
        TRUE,
        'technical_specs.pdf',
        0.90,
        'approved'
    ),
    (
        'The user interface is designed for efficiency and ease of use.',
        '사용자 인터페이스는 효율성과 사용 용이성을 위해 설계되었습니다.',
        '사용자 인터페이스는 효율성과 사용 편의성을 위해 설계되었습니다.',
        TRUE,
        'technical_specs.pdf',
        0.93,
        'approved'
    ),
    (
        'Real-time monitoring capabilities enable immediate clinical decision-making.',
        '실시간 모니터링 기능은 즉각적인 임상 의사 결정을 가능하게 합니다.',
        '실시간 모니터링 기능으로 즉각적인 임상 의사 결정이 가능합니다.',
        TRUE,
        'user_manual.pdf',
        0.91,
        'approved'
    );

-- 샘플 번역 데이터 (user_edited = 0 - 자동 번역만 있는 경우)
INSERT INTO translations (original_text, translated_text, edited_text, user_edited, file_name, confidence, review_status)
VALUES
    (
        'Contact our support team for technical assistance.',
        '기술 지원을 위해 지원팀에 문의하십시오.',
        NULL,
        FALSE,
        'user_manual.pdf',
        0.85,
        'pending'
    ),
    (
        'Product warranty is valid for 2 years from date of purchase.',
        '제품 보증은 구매일로부터 2년 동안 유효합니다.',
        NULL,
        FALSE,
        'user_manual.pdf',
        0.87,
        'pending'
    );


-- ===================================================================
-- 유용한 쿼리 예시
-- ===================================================================

-- 1. Fine-tuning용 데이터 추출 (user_edited=true)
-- SELECT original_text, edited_text 
-- FROM translations 
-- WHERE user_edited = TRUE 
-- AND edited_text IS NOT NULL
-- ORDER BY id DESC;

-- 2. 파일별 번역 통계
-- SELECT 
--     file_name,
--     COUNT(*) as total_translations,
--     SUM(CASE WHEN user_edited = TRUE THEN 1 ELSE 0 END) as edited_count,
--     AVG(confidence) as avg_confidence
-- FROM translations
-- GROUP BY file_name;

-- 3. 검토 대기 중인 번역
-- SELECT * FROM translations
-- WHERE review_status = 'pending'
-- ORDER BY created_at DESC;

-- 4. 최근 수정된 번역
-- SELECT * FROM translations
-- WHERE user_edited = TRUE
-- ORDER BY updated_at DESC
-- LIMIT 10;

-- 5. 신뢰도가 낮은 번역 (수동 검토 필요)
-- SELECT * FROM translations
-- WHERE confidence < 0.8
-- AND user_edited = FALSE
-- ORDER BY confidence ASC;


-- ===================================================================
-- 데이터베이스 사용자 생성 (선택사항)
-- ===================================================================

-- 애플리케이션 전용 사용자 생성
-- CREATE USER IF NOT EXISTS 'cadwell_app'@'localhost' IDENTIFIED BY 'your_secure_password';

-- 권한 부여
-- GRANT SELECT, INSERT, UPDATE, DELETE ON cadwell_translate.* TO 'cadwell_app'@'localhost';

-- 권한 적용
-- FLUSH PRIVILEGES;


-- 기존 translations 테이블을 MEDIUMTEXT로 마이그레이션
-- 실행 방법: mysql -u root -p cadwell_translate < backend/database/migrate_to_mediumtext.sql

USE cadwell_translate;

-- 기존 테이블 백업 (선택사항)
-- CREATE TABLE translations_backup AS SELECT * FROM translations;

-- 컬럼 타입 변경: TEXT → MEDIUMTEXT
ALTER TABLE translations 
MODIFY COLUMN original_text MEDIUMTEXT NOT NULL COMMENT '영어 원문';

ALTER TABLE translations 
MODIFY COLUMN translated_text MEDIUMTEXT COMMENT '자동 번역 텍스트';

ALTER TABLE translations 
MODIFY COLUMN edited_text MEDIUMTEXT COMMENT '사용자가 수정한 최종 번역 텍스트';

-- 확인
SHOW CREATE TABLE translations;

SELECT '마이그레이션 완료! MEDIUMTEXT로 변경되었습니다.' AS result;




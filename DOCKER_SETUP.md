# Docker Compose 실행 가이드

## 🚀 빠른 시작

### 1단계: Docker 실행

```bash
# 모든 서비스 시작 (MySQL + Backend + Frontend)
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 2단계: 서비스 확인

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **MySQL**: localhost:3306

---

## 📋 서비스 구성

### MySQL (cadwell_mysql)
- **이미지**: mysql:8.0
- **포트**: 3307
- **비밀번호**: 111111
- **데이터베이스**: cadwell_translate
- **볼륨**: mysql_data (데이터 영구 저장)
- **초기화**: `schema_mysql.sql` 자동 실행

### Backend (cadwell_api)
- **포트**: 8000
- **MySQL 연결**: mysql:3306 (Docker 네트워크 내)
- **환경 변수**: docker-compose.yml에 설정됨

### Frontend (pdf-translator-frontend)
- **포트**: 5173
- **Backend 연결**: http://localhost:8000

---

## 🔧 주요 명령어

### 서비스 시작
```bash
# 전체 시작 (백그라운드)
docker-compose up -d

# 전체 시작 (로그 보기)
docker-compose up
```

### 서비스 중지
```bash
# 중지 (컨테이너 유지)
docker-compose stop

# 중지 및 삭제
docker-compose down

# 중지 및 볼륨까지 삭제 (⚠️ 데이터 삭제)
docker-compose down -v
```

### 로그 확인
```bash
# 모든 서비스 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f backend
docker-compose logs -f mysql
```

### 컨테이너 상태 확인
```bash
# 실행 중인 컨테이너 목록
docker-compose ps

# 상세 정보
docker-compose ps -a
```

### 재빌드
```bash
# 코드 변경 후 재빌드
docker-compose up -d --build
```

---

## 🗄️ MySQL 초기화

### 자동 초기화
`docker-compose.yml` 설정에 따라 MySQL 컨테이너가 처음 시작될 때:
1. `cadwell_translate` 데이터베이스 생성
2. `schema_mysql.sql` 자동 실행
3. 샘플 데이터 8개 자동 삽입

### 수동 초기화 (필요시)

```bash
# MySQL 컨테이너 접속
docker exec -it cadwell_mysql mysql -u root -p111111

# 또는 스키마 파일 직접 실행
docker exec -i cadwell_mysql mysql -u root -p111111 cadwell_translate < backend/database/schema_mysql.sql
```

---

## 🔍 문제 해결

### MySQL 연결 오류

**증상**: `Can't connect to MySQL server`

**해결**:
```bash
# MySQL 컨테이너 상태 확인
docker-compose ps mysql

# MySQL 로그 확인
docker-compose logs mysql

# MySQL 재시작
docker-compose restart mysql
```

### 포트 충돌

**증상**: `port is already allocated`

**해결**:
```bash
# 로컬 MySQL 서비스 중지 (Windows)
net stop MySQL80

# 또는 docker-compose.yml에서 포트 변경
# mysql:
#   ports:
#     - "3307:3306"  # 로컬 포트 3307 사용
```

### 데이터베이스 초기화 실패

**해결**:
```bash
# 볼륨 삭제 후 재시작
docker-compose down -v
docker-compose up -d
```

---

## 📊 데이터 확인

### MySQL에 직접 접속

```bash
# 컨테이너 내부에서 접속
docker exec -it cadwell_mysql mysql -u root -p111111 cadwell_translate

# SQL 실행
SELECT * FROM translations;
SELECT COUNT(*) FROM translations WHERE user_edited = 1;
```

### 외부 도구로 접속

**MySQL Workbench**:
- Host: localhost
- Port: 3306
- Username: root
- Password: 111111
- Database: cadwell_translate

---

## 🔄 환경 변수 변경

### docker-compose.yml 수정

MySQL 비밀번호 변경:
```yaml
mysql:
  environment:
    - MYSQL_ROOT_PASSWORD=새_비밀번호

backend:
  environment:
    - MYSQL_PASSWORD=새_비밀번호
```

변경 후 재시작:
```bash
docker-compose up -d --force-recreate mysql backend
```

---

## 📦 볼륨 (데이터 영구 저장)

### 볼륨 목록
- `mysql_data`: MySQL 데이터 파일
- `backend_storage`: PDF 업로드/번역 파일

### 볼륨 확인
```bash
docker volume ls
```

### 볼륨 삭제 (⚠️ 주의: 데이터 삭제)
```bash
docker-compose down -v
```

---

## ✅ 완료 체크리스트

- [ ] Docker Desktop 실행 중
- [ ] `docker-compose up -d` 실행 성공
- [ ] MySQL 컨테이너 실행 중 (cadwell_mysql)
- [ ] Backend 컨테이너 실행 중 (cadwell_api)
- [ ] http://localhost:8000/docs 접속 가능
- [ ] http://localhost:5173 접속 가능
- [ ] MySQL 연결 테스트 성공
- [ ] 번역 저장 기능 테스트 성공

---

## 🎯 사용 예시

### 개발 환경에서 사용

```bash
# 1. 전체 서비스 시작
docker-compose up -d

# 2. 백엔드 로그 확인
docker-compose logs -f backend

# 3. 프론트엔드에서 번역 저장 테스트

# 4. MySQL에서 데이터 확인
docker exec -it cadwell_mysql mysql -u root -p111111 cadwell_translate -e "SELECT * FROM translations;"
```

---

## 🔐 보안 주의사항

**프로덕션 환경에서는**:
1. MySQL 비밀번호를 강력한 값으로 변경
2. `.env` 파일 사용 (비밀번호 노출 방지)
3. 포트를 외부에 노출하지 않기 (내부 네트워크만 사용)
4. 백업 자동화 설정

---

**Docker Compose로 모든 서비스를 한 번에 실행할 수 있습니다!** 🐳




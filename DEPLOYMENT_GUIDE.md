# 프로젝트 배포 가이드
## Cadwell 번역 서비스 배포 가이드

이 문서는 프로젝트를 처음 받은 사람이 배포하기 위해 필요한 모든 정보를 포함합니다.

---

## 📋 목차

1. [시스템 요구사항](#시스템-요구사항)
2. [빠른 시작 (Docker)](#빠른-시작-docker-권장)
3. [로컬 개발 환경 설정](#로컬-개발-환경-설정)
4. [환경 변수 설정](#환경-변수-설정)
5. [데이터베이스 설정](#데이터베이스-설정)
6. [API 키 설정](#api-키-설정)
7. [배포 체크리스트](#배포-체크리스트)
8. [문제 해결](#문제-해결)

---

## 시스템 요구사항

### 필수 요구사항

- **운영체제**: Windows 10+, macOS, 또는 Linux
- **Docker Desktop**: 4.0+ (Docker 방식 사용 시) **또는**
- **Node.js**: 18.0 이상
- **Python**: 3.10 이상
- **MySQL**: 8.0 이상 (Docker 미사용 시)

### 권장 사양

- **RAM**: 최소 4GB, 권장 8GB 이상
- **디스크**: 최소 5GB 여유 공간
- **인터넷**: API 호출을 위한 안정적인 연결

---

## 빠른 시작 (Docker - 권장)

가장 간단한 방법입니다. Docker만 설치되어 있으면 바로 실행 가능합니다.

### 1단계: Docker Desktop 설치

- **Windows/Mac**: https://www.docker.com/products/docker-desktop/
- 설치 후 Docker Desktop 실행

### 2단계: 프로젝트 다운로드

```bash
# Git으로 클론
git clone <repository-url>
cd gems

# 또는 ZIP 파일 압축 해제 후
cd gems
```

### 3단계: 환경 변수 설정 (선택사항)

프로젝트 루트에 `.env` 파일 생성:

```env
# OpenAI API 설정 (필수)
OPENAI_API_KEY=sk-proj-your-api-key-here

# 번역 모델 설정
OPENAI_MODEL=gpt-4o-mini
TRANSLATION_PROVIDER=openai

# MySQL 설정 (Docker Compose 사용 시 자동 설정됨)
# 로컬 MySQL 사용 시에만 필요
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=cadwell_translate

# CORS 설정
FRONTEND_ORIGIN=http://localhost:5173
```

### 4단계: Docker Compose로 실행

```bash
# 전체 서비스 시작 (MySQL + Backend + Frontend)
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 5단계: 접속 확인

- **프론트엔드**: http://localhost:5173
- **백엔드 API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs

**완료!** 🎉

---

## 로컬 개발 환경 설정

Docker 없이 직접 실행하려는 경우

### 1단계: Node.js 설치

**Windows/Mac**:
- https://nodejs.org/ 에서 LTS 버전 다운로드
- 설치 확인: `node --version` (v18 이상)

### 2단계: Python 설치

**Windows**:
- https://www.python.org/downloads/
- 설치 시 "Add Python to PATH" 체크

**Mac**:
```bash
brew install python@3.11
```

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv
```

설치 확인: `python --version` (3.10 이상)

### 3단계: MySQL 설치

**Windows**:
- https://dev.mysql.com/downloads/installer/
- 또는 XAMPP: https://www.apachefriends.org/

**Mac**:
```bash
brew install mysql
brew services start mysql
```

**Linux**:
```bash
sudo apt install mysql-server
sudo systemctl start mysql
```

### 4단계: 백엔드 설정

```bash
# 프로젝트 디렉토리로 이동
cd backend

# 가상 환경 생성
python -m venv .venv

# 가상 환경 활성화
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
```

### 5단계: 프론트엔드 설정

```bash
# 새 터미널에서
cd frontend

# 패키지 설치
npm install
```

### 6단계: 데이터베이스 설정

**MySQL 접속**:
```bash
mysql -u root -p
```

**스키마 실행**:
```bash
mysql -u root -p < backend/database/schema_mysql.sql
```

또는 MySQL Workbench에서:
1. MySQL Workbench 실행
2. `backend/database/schema_mysql.sql` 파일 열기
3. 실행 (F5)

### 7단계: 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```env
# MySQL 설정 (필수)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=cadwell_translate

# OpenAI API 설정 (필수)
OPENAI_API_KEY=sk-proj-your-api-key-here
OPENAI_MODEL=gpt-4o-mini
TRANSLATION_PROVIDER=openai

# CORS 설정
FRONTEND_ORIGIN=http://localhost:5173
```

### 8단계: 서버 실행

**터미널 1 - 백엔드**:
```bash
cd backend
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

uvicorn app.main:app --reload --port 8000
```

**터미널 2 - 프론트엔드**:
```bash
cd frontend
npm run dev
```

### 9단계: 접속 확인

- **프론트엔드**: http://localhost:5173
- **백엔드 API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs

---

## 환경 변수 설정

### 필수 환경 변수

#### 1. MySQL 데이터베이스

```env
MYSQL_HOST=localhost          # 또는 mysql (Docker 네트워크)
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password  # MySQL root 비밀번호
MYSQL_DATABASE=cadwell_translate
```

#### 2. OpenAI API

```env
OPENAI_API_KEY=sk-proj-...    # 필수! OpenAI 플랫폼에서 발급
OPENAI_MODEL=gpt-4o-mini      # 또는 ft:gpt-4o-mini-... (Fine-tuned 모델)
TRANSLATION_PROVIDER=openai
```

### 선택적 환경 변수

```env
FRONTEND_ORIGIN=http://localhost:5173
WINDOWS_MALGUN_TTF=C:\Windows\Fonts\malgun.ttf  # Windows 한글 폰트
```

### .env 파일 위치

프로젝트 루트 디렉토리에 `.env` 파일 생성:

```
gems/
├── .env                    ← 여기에 생성
├── backend/
├── frontend/
├── docker-compose.yml
└── README.md
```

---

## 데이터베이스 설정

### Docker 사용 시

자동으로 초기화됩니다. 별도 작업 불필요.

### 로컬 MySQL 사용 시

#### 1. MySQL 접속

```bash
mysql -u root -p
```

#### 2. 데이터베이스 생성 및 스키마 실행

```bash
# 방법 1: 명령줄에서
mysql -u root -p < backend/database/schema_mysql.sql

# 방법 2: MySQL Workbench에서
# backend/database/schema_mysql.sql 파일 열어서 실행
```

#### 3. 확인

```sql
USE cadwell_translate;
SHOW TABLES;
SELECT COUNT(*) FROM translations;
```

---

## API 키 설정

### OpenAI API 키 발급

1. **OpenAI 플랫폼 접속**: https://platform.openai.com/
2. **로그인 또는 회원가입**
3. **API Keys 메뉴**: https://platform.openai.com/api-keys
4. **"Create new secret key" 클릭**
5. **키 복사** (한 번만 표시됨!)
6. **`.env` 파일에 추가**:
   ```env
   OPENAI_API_KEY=sk-proj-your-actual-key-here
   ```

### Fine-tuned 모델 사용 (선택사항)

Fine-tuning을 통해 학습된 모델을 사용하려면:

```env
# 기본 모델
OPENAI_MODEL=gpt-4o-mini

# Fine-tuned 모델 (학습 후)
OPENAI_MODEL=ft:gpt-4o-mini-2024-07-18:org:cadwell-medical-ko:abc123
```

---

## 배포 체크리스트

### 초기 설정

- [ ] Node.js 18+ 설치 확인
- [ ] Python 3.10+ 설치 확인
- [ ] MySQL 8.0+ 설치 또는 Docker Desktop 설치
- [ ] 프로젝트 다운로드 완료

### 환경 설정

- [ ] `.env` 파일 생성
- [ ] MySQL 비밀번호 설정
- [ ] OpenAI API 키 발급 및 설정
- [ ] 데이터베이스 스키마 실행 (로컬 MySQL 사용 시)

### Docker 방식 (권장)

- [ ] Docker Desktop 실행 중
- [ ] `docker-compose up -d` 실행
- [ ] 모든 컨테이너 정상 실행 확인 (`docker-compose ps`)
- [ ] http://localhost:8000/docs 접속 확인

### 로컬 방식

- [ ] 백엔드 가상 환경 생성 및 패키지 설치
- [ ] 프론트엔드 패키지 설치 (`npm install`)
- [ ] MySQL 서버 실행 중
- [ ] 데이터베이스 초기화 완료
- [ ] 백엔드 서버 실행 (`uvicorn app.main:app --reload`)
- [ ] 프론트엔드 서버 실행 (`npm run dev`)
- [ ] http://localhost:5173 접속 확인

### 기능 테스트

- [ ] PDF 업로드 및 번역 테스트
- [ ] 번역 결과 표시 확인
- [ ] "번역 저장하기" 버튼 클릭
- [ ] MySQL에 데이터 저장 확인
- [ ] 에러 없이 작동 확인

---

## 문제 해결

### MySQL 연결 오류

**증상**: `Can't connect to MySQL server`

**해결**:
1. MySQL 서비스 실행 확인
   ```bash
   # Windows
   Get-Service MySQL80
   
   # Linux
   sudo systemctl status mysql
   ```

2. MySQL 서비스 시작
   ```bash
   # Windows
   net start MySQL80
   
   # Linux
   sudo systemctl start mysql
   ```

3. Docker 사용 시
   ```bash
   docker-compose restart mysql
   docker-compose logs mysql
   ```

### OpenAI API 오류

**증상**: `OPENAI_API_KEY is not set`

**해결**:
1. `.env` 파일에 `OPENAI_API_KEY` 확인
2. API 키가 올바른지 확인 (sk-proj-로 시작)
3. 백엔드 서버 재시작

### 포트 충돌

**증상**: `port is already in use`

**해결**:
1. 다른 포트 사용 중인 프로세스 종료
2. 또는 `docker-compose.yml`에서 포트 변경
3. 프론트엔드: `vite.config.ts`에서 포트 변경

### 프론트엔드 빌드 오류

**증상**: `npm install` 실패

**해결**:
```bash
# 캐시 삭제
rm -rf node_modules package-lock.json
npm cache clean --force

# 재설치
npm install
```

### 백엔드 패키지 오류

**증상**: `pip install` 실패

**해결**:
```bash
# 가상 환경 재생성
rm -rf .venv
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

---

## 배포 후 확인 사항

### 서비스 상태 확인

```bash
# Docker 방식
docker-compose ps
docker-compose logs backend
docker-compose logs mysql

# 로컬 방식
# 백엔드 로그 확인 (터미널)
# 프론트엔드 로그 확인 (터미널)
```

### API 확인

1. **Swagger UI 접속**: http://localhost:8000/docs
2. **헬스 체크**: http://localhost:8000/health
3. **번역 API 테스트**: Swagger UI에서 직접 테스트

### 데이터베이스 확인

```bash
# MySQL 접속
mysql -u root -p cadwell_translate

# 데이터 확인
SELECT COUNT(*) FROM translations;
SELECT * FROM translations WHERE user_edited = 1 LIMIT 5;
```

---

## 프로덕션 배포 주의사항

### 보안

- ✅ **`.env` 파일을 `.gitignore`에 추가** (이미 포함됨)
- ✅ **강력한 MySQL 비밀번호 사용**
- ✅ **OpenAI API 키 절대 공유하지 않기**
- ✅ **HTTPS 사용** (프로덕션 환경)
- ✅ **방화벽 설정** (필요한 포트만 개방)

### 성능

- ✅ **MySQL 인덱스 확인**
- ✅ **컨넥션 풀 설정 확인**
- ✅ **로그 레벨 조정** (프로덕션에서는 WARNING 이상)

### 백업

```bash
# 데이터베이스 백업
docker exec cadwell_mysql mysqldump -u root -p111111 cadwell_translate > backup.sql

# 또는
mysqldump -u root -p cadwell_translate > backup.sql
```

---

## 추가 리소스

### 문서

- **README.md**: 프로젝트 개요
- **FINETUNING_GUIDE.md**: Fine-tuning 가이드
- **QUICK_START.md**: 빠른 시작 가이드
- **MYSQL_SETUP.md**: MySQL 상세 설정
- **TEST_API.md**: API 테스트 가이드

### 지원

문제가 발생하면:
1. 로그 확인 (`docker-compose logs` 또는 서버 터미널)
2. 에러 메시지 전체 복사
3. 프로젝트 이슈에 등록

---

## 요약

### 최소한 필요한 것

1. **Docker Desktop** 설치
2. **`.env` 파일** 생성 (OpenAI API 키 포함)
3. **`docker-compose up -d`** 실행

### 또는

1. **Node.js, Python, MySQL** 설치
2. **`.env` 파일** 생성 및 설정
3. **스키마 실행** (`schema_mysql.sql`)
4. **서버 실행** (백엔드 + 프론트엔드)

---

**이 문서에 모든 정보가 있습니다!** 📚

문제가 발생하면 "문제 해결" 섹션을 참고하세요.



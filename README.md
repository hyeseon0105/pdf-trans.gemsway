## PDF 번역 웹앱 (React + FastAPI)

영어 PDF를 업로드하면 한국어로 번역하고, 번역된 내용을 다시 PDF로 다운로드할 수 있는 예제입니다.

### 구성
- `frontend`: React + Vite + TypeScript
- `backend`: FastAPI, PDF 추출/번역/생성

### 필요 환경
- Node.js 18+
- Python 3.10+
- Windows의 경우 한글 폰트(Malgun Gothic, `C:\Windows\Fonts\malgun.ttf`)가 있으면 번역 PDF가 한글로 정상 렌더링됩니다.

### 실행 방법
1) 백엔드
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

2) 프론트엔드(새 터미널)
```
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 로 접속하세요.

### Docker로 실행
```
docker compose up --build
```
- 프론트엔드: http://localhost:5173
- 백엔드 API: http://localhost:8000
- 번역 파일 저장 위치는 컨테이너 내부 `/app/app/storage`이며, 네임드 볼륨 `backend_storage`에 보존됩니다.
- 실제 운영 환경에서는 `FRONTEND_ORIGIN`, `VITE_API_BASE`, `WINDOWS_MALGUN_TTF` 등을 필요에 맞게 조정하세요.

## 전체 사용자 흐름
1) 사용자가 프론트에서 PDF 파일을 선택하고 “업로드 및 번역” 클릭  
2) 백엔드가 PDF에서 텍스트를 추출  
3) 설정된 번역 엔진(OpenAI 또는 googletrans)으로 한국어 번역  
4) 프론트에 번역 결과(JSON)가 반환되어 화면에 표시  
5) 사용자는 “PDF로 다운로드” 버튼으로 번역 결과를 클라이언트에서 PDF로 저장

프론트에서 문제 발생 시 로딩 표시와 에러 메시지를 보여주며, 잘못된 파일 타입(비-PDF) 업로드 시 즉시 안내합니다.

## API 구조

### POST /api/translate/pdf
- 설명: PDF 파일 업로드 → 텍스트 추출 → 번역 → 결과 반환
- 요청(FormData):
  - `file`: application/pdf
- 응답(JSON):
```json
{
  "file_id": "string",
  "translated_text": "string"
}
```
- 상태코드/오류:
  - 400: PDF 아님, 텍스트 추출 실패, 추출된 텍스트 없음
  - 500: 번역 실패, 번역 PDF 생성 실패(서버 생성 경로 사용 시)

### GET /api/download/{file_id}
- 설명: 서버에서 생성한 번역 PDF 다운로드(선택 기능)
- 응답: `application/pdf` 바이너리
- 주의: 현재 기본 흐름은 프론트에서 jsPDF로 PDF를 생성해 저장합니다. 서버 생성 PDF를 쓰고 싶다면 프론트에서 해당 엔드포인트를 호출하도록 변경하세요.

### 환경 변수
- `FRONTEND_ORIGIN`: CORS 허용 오리진 (기본: `http://localhost:5173`)
- `WINDOWS_MALGUN_TTF`: ReportLab에서 사용할 한글 폰트 경로 (기본: `C:\Windows\Fonts\malgun.ttf`)
- 프론트엔드에서 백엔드 주소 변경 시 `.env` 파일에 `VITE_API_BASE=http://localhost:8000` 지정 가능
  - 지정하지 않으면 자동으로 현재 호스트의 8000 포트를 바라봅니다.

#### 번역 엔진 설정
- `TRANSLATION_PROVIDER`: `openai` 또는 `google` (기본: `openai`)
- `OPENAI_API_KEY`: OpenAI 사용 시 필수 (없으면 번역이 실패합니다)
- `OPENAI_MODEL`: OpenAI 모델 지정 (기본: `gpt-4o-mini`)
- `GOOGLE_APPLICATION_CREDENTIALS`: Google Cloud Translate 사용 시 서비스 계정 JSON 파일 경로 (없으면 번역이 실패합니다)

예시 (Windows PowerShell):
```
$env:TRANSLATION_PROVIDER="openai"
$env:OPENAI_API_KEY="sk-********"
$env:OPENAI_MODEL="gpt-4o-mini"
uvicorn app.main:app --reload --port 8000
```

Docker Compose로 OpenAI 사용하기:
`docker compose` 실행 전에 다음을 추가 설정(예: `.env` 파일)로 주입하세요.
```
# .env
TRANSLATION_PROVIDER=openai
OPENAI_API_KEY=sk-********
OPENAI_MODEL=gpt-4o-mini
```
그리고 `docker-compose.yml`은 기본적으로 위 환경변수를 읽어옵니다. (Compose가 같은 디렉터리의 `.env`를 자동 로드)

Google Cloud Translate 사용 예:
```
# .env
TRANSLATION_PROVIDER=google
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp_sa.json
```
컨테이너에 서비스 계정 키를 마운트(또는 Docker secret)해 주세요.

> ⚠️ `OPENAI_API_KEY` 혹은 `GOOGLE_APPLICATION_CREDENTIALS`가 설정되지 않으면 번역이 실패하며, 백엔드가 명시적인 오류 메시지를 반환합니다.

### 참고
- 번역은 기본적으로 OpenAI를 사용하며, 설정에 따라 Google Cloud Translate로 전환할 수 있습니다. 키/권한 문제가 있을 경우 원문이 반환될 수 있습니다.
- PDF 텍스트 추출은 `pypdf`를 사용하며, 스캔(pdf)·이미지 기반 PDF는 OCR이 없어 텍스트 추출이 어렵습니다.



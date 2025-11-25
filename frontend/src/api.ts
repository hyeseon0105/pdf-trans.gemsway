const API_BASE = resolveApiBase()

function resolveApiBase(): string {
  const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined
  if (envBase && typeof envBase === 'string' && envBase.trim().length > 0) {
    return envBase.replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    try {
      const url = new URL(window.location.origin)
      // 기본 dev 포트 5173 → 백엔드 8000으로 치환
      url.port = '8000'
      return url.toString().replace(/\/$/, '')
    } catch {
      // ignore
    }
  }
  return 'http://localhost:8000'
}

export type LayoutBlock = {
  bbox: [number, number, number, number]
  text: string
  translated_text?: string
  font_size?: number
  text_start_x?: number  // Original text start position for alignment
}

export type LayoutPage = {
  width: number
  height: number
  blocks: LayoutBlock[]
}

export type ReviewResult = {
  english: string | null
  korean: string | null
  status: string
  similarity: number
  suggestion: string | null
}

export type ReviewSummary = {
  total_paragraphs: number
  ok_count: number
  warning_count: number
  missing_count: number
  accuracy_percent: number
}

export type ReviewData = {
  results: ReviewResult[]
  summary: ReviewSummary
}

export type TranslateResponse = {
  uploadId: string
  fileId: string
  originalText: string
  translatedText: string
  layout?: { pages: LayoutPage[] }
  preview?: { id: string, count: number }
  review?: ReviewData
}

export function getUploadPdfUrl(uploadId: string): string {
  return `${API_BASE}/api/uploads/${uploadId}`
}

export function getPreviewImageUrl(previewId: string, pageIndex1Based: number): string {
  return `${API_BASE}/api/preview/${previewId}/${pageIndex1Based}`
}

export function getTextOverlayUrl(previewId: string, pageIndex1Based: number, textIndex: number): string {
  return `${API_BASE}/api/preview/${previewId}/${pageIndex1Based}/text/${textIndex}`
}

export async function uploadAndTranslatePdf(
  file: File,
  onProgress?: (percent: number) => void
): Promise<TranslateResponse> {
  return new Promise((resolve, reject) => {
  const formData = new FormData()
  formData.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api/translate/pdf`)
    xhr.responseType = 'json'
    // 큰 파일 처리를 위해 타임아웃을 30분(1800000ms)으로 설정
    xhr.timeout = 30 * 60 * 1000

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const data = xhr.response ?? {}
        resolve({
          originalText: data.original_text ?? '',
          translatedText: data.translated_text ?? '',
          fileId: data.file_id ?? '',
          uploadId: data.upload_id ?? '',
          layout: data.layout ?? undefined,
          preview: data.preview ?? undefined,
          review: data.review ?? undefined
        })
      } else {
        try {
          const resp = new Response(xhr.response ?? xhr.responseText, { status: xhr.status })
    const msg = await safeError(resp)
          reject(new Error(msg))
        } catch {
          reject(new Error(`요청 실패 (${xhr.status})`))
        }
      }
    }

    xhr.onerror = () => {
      reject(new Error('네트워크 오류가 발생했습니다.'))
    }

    xhr.ontimeout = () => {
      reject(new Error('요청 시간이 초과되었습니다. 파일이 너무 크거나 서버 처리 시간이 오래 걸립니다.'))
    }

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100)
          onProgress(Math.min(99, percent))
        } else {
          onProgress(50)
        }
      }
      xhr.upload.onload = () => {
        onProgress(100)
      }
    }

    xhr.send(formData)
  })
}

export async function downloadTranslatedPdf(fileId: string): Promise<Blob> {
  try {
    console.log(`[PDF 다운로드] 시작: fileId=${fileId}`)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 10 * 60 * 1000) // 10분 타임아웃
    
    const resp = await fetch(`${API_BASE}/api/download/${fileId}`, {
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    
    if (!resp.ok) {
      const msg = await safeError(resp)
      console.error(`[PDF 다운로드] 실패: ${resp.status} - ${msg}`)
      throw new Error(msg)
    }
    
    console.log(`[PDF 다운로드] 응답 받음, 크기: ${resp.headers.get('content-length') || '알 수 없음'} bytes`)
    const blob = await resp.blob()
    console.log(`[PDF 다운로드] 완료: ${blob.size} bytes`)
    return blob
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.error('[PDF 다운로드] 타임아웃 발생')
      throw new Error('다운로드 시간이 초과되었습니다. 파일이 너무 큽니다.')
    }
    console.error(`[PDF 다운로드] 오류:`, error)
    throw error
  }
}

async function safeError(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    return data?.detail ?? `요청 실패 (${resp.status})`
  } catch {
    return `요청 실패 (${resp.status})`
  }
}

// 번역 데이터 저장 타입
export type SaveTranslationRequest = {
  original_text: string
  translated_text?: string
  edited_text?: string
  user_edited: boolean
  file_name?: string
  confidence?: number
}

export type SaveTranslationResponse = {
  id: number
  message: string
  original_text: string
  user_edited: boolean
}

/**
 * 번역 데이터를 MySQL 데이터베이스에 저장합니다.
 * 
 * @param data 저장할 번역 데이터
 * @returns 저장된 번역 데이터 정보
 */
export async function saveTranslation(data: SaveTranslationRequest): Promise<SaveTranslationResponse> {
  try {
    console.log('[번역 저장] 요청 데이터:', data)
    
    const resp = await fetch(`${API_BASE}/api/translations/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    })

    console.log('[번역 저장] 응답 상태:', resp.status, resp.statusText)

    if (!resp.ok) {
      // 상세한 에러 메시지 파싱
      const errorData = await resp.json()
      console.error('[번역 저장] 에러 상세:', errorData)
      
      // FastAPI 유효성 검사 에러 형식 처리
      if (errorData.detail && Array.isArray(errorData.detail)) {
        console.error('[번역 저장] 유효성 검사 에러:', errorData.detail)
        const errors = errorData.detail.map((err: any) => 
          `${err.loc?.join(' > ')} : ${err.msg}`
        ).join('\n')
        throw new Error(`데이터 검증 실패:\n${errors}`)
      } else if (errorData.detail) {
        throw new Error(errorData.detail)
      } else {
        throw new Error(JSON.stringify(errorData))
      }
    }

    const result = await resp.json()
    console.log('[번역 저장] 성공:', result)
    return result
  } catch (error: any) {
    console.error('[번역 저장] 오류:', error)
    throw error
  }
}

// 파인튜닝 관련 타입 및 함수
export type FinetuningStatus = {
  status: string
  message: string
  data_count: number
  min_count: number
  can_train: boolean
  job_id?: string
  model_id?: string
}

export type FinetuningStartResponse = {
  status: string
  message: string
  job_id?: string
  data_count: number
  min_count: number
}

export async function getFinetuningStatus(): Promise<FinetuningStatus> {
  const resp = await fetch(`${API_BASE}/api/finetuning/status`)
  if (!resp.ok) {
    const error = await resp.json()
    throw new Error(error.detail || '상태 확인 실패')
  }
  return resp.json()
}

export async function startFinetuning(): Promise<FinetuningStartResponse> {
  const resp = await fetch(`${API_BASE}/api/finetuning/start`, {
    method: 'POST',
  })
  if (!resp.ok) {
    const error = await resp.json()
    throw new Error(error.detail || '학습 시작 실패')
  }
  return resp.json()
}

export async function getFinetuningJobStatus(jobId: string): Promise<{
  job_id: string
  status: string
  model: string
  fine_tuned_model?: string
  created_at: number
  finished_at?: number
  trained_tokens?: number
  error?: any
  env_updated?: boolean
  message?: string
}> {
  const resp = await fetch(`${API_BASE}/api/finetuning/job/${jobId}`)
  if (!resp.ok) {
    const error = await resp.json()
    throw new Error(error.detail || '작업 상태 확인 실패')
  }
  return resp.json()
}



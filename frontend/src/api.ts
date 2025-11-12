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
  review?: ReviewData
}

export function getUploadPdfUrl(uploadId: string): string {
  return `${API_BASE}/api/uploads/${uploadId}`
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

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const data = xhr.response ?? {}
        resolve({
          originalText: data.original_text ?? '',
          translatedText: data.translated_text ?? '',
          fileId: data.file_id ?? '',
          uploadId: data.upload_id ?? '',
          layout: data.layout ?? undefined,
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
  const resp = await fetch(`${API_BASE}/api/download/${fileId}`)
  if (!resp.ok) {
    const msg = await safeError(resp)
    throw new Error(msg)
  }
  return await resp.blob()
}

async function safeError(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    return data?.detail ?? `요청 실패 (${resp.status})`
  } catch {
    return `요청 실패 (${resp.status})`
  }
}



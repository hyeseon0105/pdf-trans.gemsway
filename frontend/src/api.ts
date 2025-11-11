const API_BASE = resolveApiBase()

function resolveApiBase(): string {
  const envBase = import.meta.env.VITE_API_BASE
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

export async function uploadAndTranslatePdf(file: File): Promise<{ translatedText: string; fileId: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch(`${API_BASE}/api/translate/pdf`, {
    method: 'POST',
    body: formData
  })
  if (!resp.ok) {
    const msg = await safeError(resp)
    throw new Error(msg)
  }
  const data = await resp.json()
  return { translatedText: data.translated_text ?? '', fileId: data.file_id ?? '' }
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



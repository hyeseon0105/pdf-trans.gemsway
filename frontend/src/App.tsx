import { useRef, useState } from 'react'
import { uploadAndTranslatePdf, downloadTranslatedPdf, getUploadPdfUrl, type TranslateResponse } from './api'
import { generatePdfFromText } from './pdf'
import { PdfUploader } from './components/PdfUploader'
import { TranslationResult } from './components/TranslationResult'
import { DesignPreview, type DesignPreviewHandle } from './components/DesignPreview'

function App() {
  const [translatedText, setTranslatedText] = useState<string>('')
  const [fileId, setFileId] = useState<string>('')
  const [uploadId, setUploadId] = useState<string>('')
  const [layout, setLayout] = useState<TranslateResponse['layout']>()
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [originalFileName, setOriginalFileName] = useState<string>('')
  const [previewMode, setPreviewMode] = useState<boolean>(false)
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const previewRef = useRef<DesignPreviewHandle | null>(null)

  const handleUpload = async (file: File) => {
    setError('')
    setLoading(true)
    setTranslatedText('')
    setFileId('')
    setUploadId('')
    setLayout(undefined)
    setOriginalFileName(file.name)
    setPreviewMode(false)
    setUploadProgress(0)
    try {
      if (file.type !== 'application/pdf') {
        throw new Error('PDF 파일만 업로드할 수 있습니다.')
      }
      const result = await uploadAndTranslatePdf(file, (percent: number) => {
        setUploadProgress(percent)
      })
      setTranslatedText(result.translatedText)
      setFileId(result.fileId)
      setUploadId(result.uploadId)
      setLayout(result.layout)
    } catch (e: any) {
      setError(e?.message ?? '업로드/번역 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
      setUploadProgress(0)
    }
  }

  const handleServerPdfDownload = async () => {
    const base = originalFileName?.replace(/\.[^/.]+$/, '') || 'document'
    const out = `translated_${base}.pdf`
    try {
      if (fileId) {
        const blob = await downloadTranslatedPdf(fileId)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = out
        a.click()
        URL.revokeObjectURL(url)
        return
      }
      // 안전망: 서버 fileId가 없다면 클라이언트에서 생성
      generatePdfFromText(translatedText, out)
    } catch (e: any) {
      setError(e?.message ?? '다운로드 중 오류가 발생했습니다.')
    }
  }

  const handlePreviewDownload = async () => {
    const base = originalFileName?.replace(/\.[^/.]+$/, '') || 'document'
    const out = `translated_layout_${base}.pdf`
    try {
      await previewRef.current?.exportPdf(out)
    } catch (e: any) {
      setError(e?.message ?? '미리보기 PDF 생성 중 오류가 발생했습니다.')
    }
  }

  return (
    <div className="container">
      {loading && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 999,
          }}
        >
          <div
            style={{
              width: '320px',
              padding: '24px',
              borderRadius: 16,
              backgroundColor: '#ffffff',
              boxShadow: '0 20px 40px rgba(0,0,0,0.25)',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              alignItems: 'stretch',
            }}
          >
            <div style={{ fontSize: 18, fontWeight: 600, color: '#111' }}>
              {uploadProgress > 0 && uploadProgress < 100
                ? `업로드 중... ${uploadProgress}%`
                : uploadProgress >= 100
                ? '업로드 완료! 번역을 처리하고 있습니다...'
                : '준비 중입니다...'}
            </div>
            <div
              style={{
                height: 12,
                borderRadius: 999,
                backgroundColor: 'rgba(0,0,0,0.08)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${Math.min(uploadProgress, 100)}%`,
                  height: '100%',
                  transition: 'width 0.2s ease',
                  background: 'linear-gradient(90deg, #4f46e5, #6366f1)',
                }}
              />
            </div>
            <div style={{ fontSize: 14, color: '#555' }}>
              {uploadProgress < 100
                ? 'PDF를 서버로 업로드하는 중입니다.'
                : '번역 모델이 텍스트를 변환하는 중입니다.'}
            </div>
          </div>
        </div>
      )}
      <h1>PDF 영어→한국어 번역</h1>
      <p className="subtitle">PDF를 업로드하면 자동으로 한국어로 번역합니다.</p>
      <PdfUploader onUpload={handleUpload} disabled={loading} />
      {error && <p className="error">{error}</p>}
      {!previewMode && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <button onClick={() => setPreviewMode(true)} disabled={!uploadId || !layout}>
              → 원본 디자인 미리보기
            </button>
          </div>
      <TranslationResult text={translatedText} onDownload={handleServerPdfDownload} canDownload={!!translatedText} />
        </>
      )}
      {previewMode && uploadId && (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <button onClick={() => setPreviewMode(false)}>← 번역 텍스트 보기</button>
            <button onClick={handlePreviewDownload} disabled={!layout || !layout?.pages?.length}>
              PDF로 다운로드
            </button>
          </div>
          <DesignPreview ref={previewRef} pdfUrl={getUploadPdfUrl(uploadId)} pages={layout?.pages} />
        </div>
      )}
    </div>
  )
}

export default App



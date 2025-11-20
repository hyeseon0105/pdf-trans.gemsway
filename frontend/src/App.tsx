import { useRef, useState } from 'react'
import { uploadAndTranslatePdf, downloadTranslatedPdf, getUploadPdfUrl, getPreviewImageUrl, type TranslateResponse } from './api'
import { generatePdfFromText } from './pdf'
import { PdfUploader } from './components/PdfUploader'
import { TranslationResult } from './components/TranslationResult'
import { DesignPreview, type DesignPreviewHandle } from './components/DesignPreview'

function App() {
  const [originalText, setOriginalText] = useState<string>('')
  const [translatedText, setTranslatedText] = useState<string>('')
  const [fileId, setFileId] = useState<string>('')
  const [uploadId, setUploadId] = useState<string>('')
  const [layout, setLayout] = useState<TranslateResponse['layout']>()
  const [preview, setPreview] = useState<TranslateResponse['preview']>()
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [originalFileName, setOriginalFileName] = useState<string>('')
  const [previewMode, setPreviewMode] = useState<boolean>(false)
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const [downloading, setDownloading] = useState<boolean>(false)
  const previewRef = useRef<DesignPreviewHandle | null>(null)

  const handleUpload = async (file: File) => {
    setError('')
    setLoading(true)
    setOriginalText('')
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
      setOriginalText(result.originalText)
      setTranslatedText(result.translatedText)
      setFileId(result.fileId)
      setUploadId(result.uploadId)
      setLayout(result.layout)
      setPreview(result.preview)
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
    setError('')
    setDownloading(true)
    try {
      console.log('[다운로드] 시작:', { fileId, translatedTextLength: translatedText.length })
      if (fileId) {
        console.log('[다운로드] 서버 PDF 다운로드 시도')
        const blob = await downloadTranslatedPdf(fileId)
        console.log('[다운로드] 서버 PDF 받음, 크기:', blob.size, 'bytes')
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = out
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        console.log('[다운로드] 완료')
        return
      }
      // 안전망: 서버 fileId가 없다면 클라이언트에서 생성
      console.log('[다운로드] 클라이언트 PDF 생성')
      generatePdfFromText(translatedText, out)
      console.log('[다운로드] 클라이언트 PDF 생성 완료')
    } catch (e: any) {
      console.error('[다운로드] 오류:', e)
      setError(e?.message ?? '다운로드 중 오류가 발생했습니다.')
    } finally {
      setDownloading(false)
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

  const handlePreviewWordDownload = async () => {
    const base = originalFileName?.replace(/\.[^/.]+$/, '') || 'document'
    const out = `translated_layout_${base}.docx`
    try {
      await previewRef.current?.exportDocx(out)
    } catch (e: any) {
      setError(e?.message ?? '미리보기 워드 생성 중 오류가 발생했습니다.')
    }
  }


  return (
    <div className="container" style={{ paddingLeft: '0', paddingRight: '0', marginLeft: '0', marginRight: '0', textAlign: 'left' }}>
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
      <TranslationResult 
        originalText={originalText} 
        translatedText={translatedText} 
        onDownload={handleServerPdfDownload} 
        canDownload={!!translatedText && !downloading} 
      />
      {downloading && (
        <div style={{ marginTop: 8, padding: 12, backgroundColor: '#f0f0f0', borderRadius: 4 }}>
          PDF 다운로드 중... (큰 파일의 경우 시간이 걸릴 수 있습니다)
        </div>
      )}
        </>
      )}
      {previewMode && uploadId && (
        <div style={{ marginTop: 12, marginLeft: '0', paddingLeft: '0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, marginLeft: '0' }}>
            <button onClick={() => setPreviewMode(false)}>← 번역 텍스트 보기</button>
            <button onClick={handlePreviewDownload} disabled={!layout || !layout?.pages?.length}>
              PDF로 다운로드
            </button>
            <button onClick={handlePreviewWordDownload} disabled={!layout || !layout?.pages?.length}>
              워드로 다운로드
            </button>
          </div>
          <DesignPreview
            ref={previewRef}
            pdfUrl={getUploadPdfUrl(uploadId)}
            pages={layout?.pages}
            bgImages={preview?.id && preview?.count ? Array.from({ length: preview.count }).map((_, i) => getPreviewImageUrl(preview.id, i + 1)) : undefined}
            previewId={preview?.id}
          />
        </div>
      )}
    </div>
  )
}

export default App



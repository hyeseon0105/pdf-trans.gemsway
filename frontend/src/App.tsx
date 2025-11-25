import { useRef, useState, useEffect } from 'react'
import { uploadAndTranslatePdf, downloadTranslatedPdf, getUploadPdfUrl, getPreviewImageUrl, type TranslateResponse, getFinetuningStatus, startFinetuning, getFinetuningJobStatus, type FinetuningStatus } from './api'
import { generatePdfFromText } from './pdf'
import { PdfUploader } from './components/PdfUploader'
import { TranslationResult } from './components/TranslationResult'
import { DesignPreview, type DesignPreviewHandle } from './components/DesignPreview'

function App() {
  const [originalText, setOriginalText] = useState<string>('')
  const [translatedText, setTranslatedText] = useState<string>('')
  const [manualTranslation, setManualTranslation] = useState<string>('')
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
  const [finetuningStatus, setFinetuningStatus] = useState<FinetuningStatus | null>(null)
  const [finetuningLoading, setFinetuningLoading] = useState<boolean>(false)
  const [finetuningError, setFinetuningError] = useState<string>('')
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<any>(null)

  // 파인튜닝 상태 로드
  useEffect(() => {
    const loadFinetuningStatus = async () => {
      try {
        const status = await getFinetuningStatus()
        setFinetuningStatus(status)
        setFinetuningError('') // 성공 시 에러 초기화
      } catch (e: any) {
        // 연결 실패는 조용히 처리 (백엔드가 실행되지 않았을 수 있음)
        const errorMessage = e?.message || String(e)
        if (errorMessage.includes('Failed to fetch') || errorMessage.includes('ERR_CONNECTION_REFUSED')) {
          // 백엔드 서버가 실행되지 않은 경우 - 조용히 처리
          setFinetuningStatus(null)
          setFinetuningError('백엔드 서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인하세요.')
        } else {
          // 기타 에러는 표시
          console.error('파인튜닝 상태 로드 실패:', e)
          setFinetuningError(errorMessage)
        }
      }
    }
    loadFinetuningStatus()
    // 30초마다 상태 업데이트 (연결 실패 시에도 재시도)
    const interval = setInterval(loadFinetuningStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleUpload = async (file: File) => {
    setError('')
    setLoading(true)
    setOriginalText('')
    setTranslatedText('')
    setManualTranslation('')
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
      
      {/* 헤더 및 로고 */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '1rem 2rem',
        borderBottom: '1px solid #e0e0e0',
        marginBottom: '2rem',
        backgroundColor: '#ffffff'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginLeft: '-2rem', paddingLeft: '5px' }}>
          {/* 로고 - 이미지 파일이 있으면 이미지 사용, 없으면 텍스트 */}
          <div style={{ position: 'relative', height: '40px', display: 'flex', alignItems: 'center' }}>
            <img 
              src="/logo.png" 
              alt="GEMSway" 
              style={{
                height: '40px',
                width: 'auto',
                maxWidth: '200px',
                objectFit: 'contain',
                display: 'block'
              }}
              onError={(e) => {
                // 이미지 로드 실패 시 숨김
                const target = e.target as HTMLImageElement
                target.style.display = 'none'
                // 텍스트 로고 표시
                const fallback = target.nextElementSibling as HTMLElement
                if (fallback) {
                  fallback.style.display = 'flex'
                }
              }}
            />
            {/* 이미지가 없을 때 표시할 텍스트 로고 */}
            <div 
              className="logo-text-fallback"
              style={{
                display: 'none',
                height: '40px',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '24px',
                fontWeight: 'bold',
                color: '#4f46e5',
                fontFamily: 'system-ui, sans-serif',
                whiteSpace: 'nowrap'
              }}
            >
              GEMSway
            </div>
          </div>
        </div>
      </header>
      
      <h1>PDF 영어→한국어 번역</h1>
      <p className="subtitle">PDF를 업로드하면 자동으로 한국어로 번역합니다.</p>
      
      {/* 파인튜닝 섹션 */}
      <div style={{ 
        marginBottom: 24, 
        padding: 16, 
        backgroundColor: '#f8f9fa', 
        borderRadius: 8,
        border: '1px solid #e0e0e0'
      }}>
        <h3 style={{ marginTop: 0, marginBottom: 12 }}>파인튜닝 모델 학습</h3>
        {finetuningStatus && (
          <div style={{ marginBottom: 12 }}>
            <p style={{ margin: '4px 0', fontSize: 14 }}>
              학습 데이터: <strong>{finetuningStatus.data_count}개</strong> / 최소 요구사항: {finetuningStatus.min_count}개
            </p>
            <p style={{ margin: '4px 0', fontSize: 14, color: finetuningStatus.can_train ? '#059669' : '#dc2626' }}>
              {finetuningStatus.message}
            </p>
          </div>
        )}
        <button
          onClick={async () => {
            setFinetuningLoading(true)
            setFinetuningError('')
            try {
              const result = await startFinetuning()
              alert(`✅ ${result.message}\n\n작업 ID: ${result.job_id}\n\n학습이 진행 중입니다. 완료되면 자동으로 모델 ID가 업데이트됩니다.`)
              // 상태 새로고침
              const status = await getFinetuningStatus()
              setFinetuningStatus(status)
              
              // 작업 ID 저장 및 상태 확인 시작
              if (result.job_id) {
                setCurrentJobId(result.job_id)
                // 즉시 상태 확인 시작
                const checkJobStatus = async () => {
                  try {
                    const status = await getFinetuningJobStatus(result.job_id!)
                    setJobStatus(status)
                    
                    if (status.status === 'succeeded' && status.fine_tuned_model) {
                      if (status.env_updated) {
                        alert(`🎉 학습 완료!\n\n${status.message}\n\n컨테이너를 재시작하면 새 모델이 적용됩니다:\ndocker-compose restart backend`)
                      } else {
                        alert(`🎉 학습 완료!\n\n모델 ID: ${status.fine_tuned_model}\n\n.env 파일에 다음을 추가하세요:\nOPENAI_MODEL=${status.fine_tuned_model}`)
                      }
                      setCurrentJobId(null) // 완료되면 상태 확인 중지
                    } else if (status.status === 'failed') {
                      alert(`❌ 학습 실패: ${status.error || '알 수 없는 오류'}`)
                      setCurrentJobId(null)
                    } else if (status.status === 'validating_files' || status.status === 'queued' || status.status === 'running') {
                      // 진행 중이면 10초 후 다시 확인
                      setTimeout(checkJobStatus, 10000)
                    } else {
                      // 기타 상태도 30초 후 확인
                      setTimeout(checkJobStatus, 30000)
                    }
                  } catch (e) {
                    console.error('작업 상태 확인 실패:', e)
                    // 오류 발생 시 30초 후 재시도
                    setTimeout(checkJobStatus, 30000)
                  }
                }
                // 즉시 첫 확인
                checkJobStatus()
              }
            } catch (e: any) {
              setFinetuningError(e.message || '학습 시작 실패')
            } finally {
              setFinetuningLoading(false)
            }
          }}
          disabled={!finetuningStatus?.can_train || finetuningLoading}
          style={{
            padding: '10px 20px',
            fontSize: 16,
            backgroundColor: finetuningStatus?.can_train ? '#4f46e5' : '#9ca3af',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            cursor: finetuningStatus?.can_train ? 'pointer' : 'not-allowed',
            fontWeight: 'bold'
          }}
        >
          {finetuningLoading ? '학습 시작 중...' : '학습하기'}
        </button>
        {finetuningError && (
          <p style={{ marginTop: 8, color: '#dc2626', fontSize: 14 }}>{finetuningError}</p>
        )}
        {currentJobId && jobStatus && (
          <div style={{ 
            marginTop: 12, 
            padding: 12, 
            backgroundColor: '#f0f9ff', 
            borderRadius: 6,
            border: '1px solid #bae6fd'
          }}>
            <p style={{ margin: '4px 0', fontSize: 14, fontWeight: 'bold' }}>
              학습 진행 중...
            </p>
            <p style={{ margin: '4px 0', fontSize: 12, color: '#666' }}>
              작업 ID: {currentJobId}
            </p>
            <p style={{ margin: '4px 0', fontSize: 12, color: '#666' }}>
              상태: {jobStatus.status === 'queued' ? '대기 중' : 
                     jobStatus.status === 'validating_files' ? '파일 검증 중' :
                     jobStatus.status === 'running' ? '학습 진행 중' :
                     jobStatus.status === 'succeeded' ? '✅ 완료' :
                     jobStatus.status === 'failed' ? '❌ 실패' :
                     jobStatus.status}
            </p>
            {jobStatus.fine_tuned_model && (
              <p style={{ margin: '4px 0', fontSize: 12, color: '#059669', fontWeight: 'bold' }}>
                모델 ID: {jobStatus.fine_tuned_model}
              </p>
            )}
            {jobStatus.trained_tokens && (
              <p style={{ margin: '4px 0', fontSize: 12, color: '#666' }}>
                학습된 토큰: {jobStatus.trained_tokens.toLocaleString()}개
              </p>
            )}
          </div>
        )}
        <p style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
          💡 데이터가 {finetuningStatus?.min_count || 30}개 이상 모였을 때만 학습할 수 있습니다.
        </p>
      </div>
      
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
        userTranslation={manualTranslation}
        onUserTranslationChange={setManualTranslation}
        fileName={originalFileName}
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



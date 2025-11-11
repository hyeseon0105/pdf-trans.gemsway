import { useState } from 'react'
import { uploadAndTranslatePdf, downloadTranslatedPdf } from './api'
import { generatePdfFromText } from './pdf'
import { PdfUploader } from './components/PdfUploader'
import { TranslationResult } from './components/TranslationResult'

function App() {
  const [translatedText, setTranslatedText] = useState<string>('')
  const [fileId, setFileId] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [originalFileName, setOriginalFileName] = useState<string>('')

  const handleUpload = async (file: File) => {
    setError('')
    setLoading(true)
    setTranslatedText('')
    setFileId('')
    setOriginalFileName(file.name)
    try {
      if (file.type !== 'application/pdf') {
        throw new Error('PDF 파일만 업로드할 수 있습니다.')
      }
      const result = await uploadAndTranslatePdf(file)
      setTranslatedText(result.translatedText)
      setFileId(result.fileId)
    } catch (e: any) {
      setError(e?.message ?? '업로드/번역 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
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

  return (
    <div className="container">
      <h1>PDF 영어→한국어 번역</h1>
      <p className="subtitle">PDF를 업로드하면 자동으로 한국어로 번역합니다.</p>
      <PdfUploader onUpload={handleUpload} disabled={loading} />
      {loading && <p>번역 중입니다. 잠시만 기다려주세요...</p>}
      {error && <p className="error">{error}</p>}
      <TranslationResult text={translatedText} onDownload={handleServerPdfDownload} canDownload={!!translatedText} />
    </div>
  )
}

export default App



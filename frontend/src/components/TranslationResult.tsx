type Props = {
  originalText: string
  translatedText: string
  canDownload: boolean
  onDownload: () => void
}

export function TranslationResult({ originalText, translatedText, canDownload, onDownload }: Props) {
  if (!translatedText) return null
  return (
    <div className="result">
      <div className="result-header">
        <h2>번역 결과</h2>
        <button onClick={onDownload} disabled={!canDownload}>
          PDF로 다운로드
        </button>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px',
        marginTop: '16px'
      }}>
        <div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 600, color: '#000000' }}>
            원문
          </h3>
          <pre className="result-text" style={{
            margin: 0,
            padding: '16px',
            backgroundColor: '#ffffff',
            color: '#000000',
            borderRadius: '8px',
            border: '1px solid #e0e0e0',
            fontSize: '14px',
            lineHeight: '1.6',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: '600px',
            overflowY: 'auto'
          }}>
            {originalText}
          </pre>
        </div>
        <div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 600, color: '#000000' }}>
            번역문
          </h3>
          <pre className="result-text" style={{
            margin: 0,
            padding: '16px',
            backgroundColor: '#ffffff',
            color: '#000000',
            borderRadius: '8px',
            border: '1px solid #e0e0e0',
            fontSize: '14px',
            lineHeight: '1.6',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: '600px',
            overflowY: 'auto'
          }}>
            {translatedText}
          </pre>
        </div>
      </div>
    </div>
  )
}



type Props = {
  text: string
  canDownload: boolean
  onDownload: () => void
}

export function TranslationResult({ text, canDownload, onDownload }: Props) {
  if (!text) return null
  return (
    <div className="result">
      <div className="result-header">
        <h2>번역 결과</h2>
        <button onClick={onDownload} disabled={!canDownload}>
          PDF로 다운로드
        </button>
      </div>
      <pre className="result-text">{text}</pre>
    </div>
  )
}



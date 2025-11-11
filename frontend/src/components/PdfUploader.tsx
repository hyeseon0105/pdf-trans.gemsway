import { useRef, useState } from 'react'

type Props = {
  onUpload: (file: File) => Promise<void> | void
  disabled?: boolean
}

export function PdfUploader({ onUpload, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [localError, setLocalError] = useState<string>('')

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.type !== 'application/pdf') {
      setLocalError('PDF 파일만 업로드할 수 있습니다.')
      setFileName('')
      return
    }
    setLocalError('')
    setFileName(file.name)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const file = inputRef.current?.files?.[0]
    if (!file) {
      setLocalError('파일을 선택해주세요.')
      return
    }
    if (file.type !== 'application/pdf') {
      setLocalError('PDF 파일만 업로드할 수 있습니다.')
      return
    }
    await onUpload(file)
  }

  return (
    <form className="uploader" onSubmit={handleSubmit}>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={handleChange}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled}>
        {disabled ? '업로드 중...' : '업로드 및 번역'}
      </button>
      {fileName && <span className="file-name">{fileName}</span>}
      {localError && <span className="error">{localError}</span>}
    </form>
  )
}



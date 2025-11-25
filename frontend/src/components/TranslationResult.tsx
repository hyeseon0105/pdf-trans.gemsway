import { useState } from 'react'
import { saveTranslation } from '../api'
import * as XLSX from 'xlsx'

type Props = {
  originalText: string
  translatedText: string
  canDownload: boolean
  onDownload: () => void
  /** 사용자가 직접 작성하는 번역문 */
  userTranslation: string
  /** 사용자가 직접 작성한 번역문 변경 핸들러 */
  onUserTranslationChange: (value: string) => void
  /** 파일명 (선택사항) */
  fileName?: string
}

export function TranslationResult({
  originalText,
  translatedText,
  canDownload,
  onDownload,
  userTranslation,
  onUserTranslationChange,
  fileName,
}: Props) {
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)

  // 번역 데이터 저장 함수
  const handleSave = async () => {
    // 원문이 없으면 저장 불가
    if (!originalText.trim()) {
      setSaveMessage({ type: 'error', text: '원문이 없어 저장할 수 없습니다.' })
      setTimeout(() => setSaveMessage(null), 3000)
      return
    }

    // 사용자가 직접 번역한 텍스트가 있으면 edited_text로, 없으면 translated_text로 저장
    const editedText = userTranslation.trim() || undefined
    const shouldMarkAsEdited = !!editedText && editedText !== translatedText

    setIsSaving(true)
    setSaveMessage(null)

    try {
      const result = await saveTranslation({
        original_text: originalText,
        translated_text: translatedText || undefined,
        edited_text: editedText,
        user_edited: shouldMarkAsEdited,
        file_name: fileName,
        confidence: 0.95, // 사용자가 직접 수정한 경우 높은 신뢰도
      })

      setSaveMessage({
        type: 'success',
        text: `저장 완료! (ID: ${result.id})`
      })

      // 3초 후 메시지 자동 제거
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (error: any) {
      console.error('번역 저장 실패:', error)
      setSaveMessage({
        type: 'error',
        text: error.message || '저장 중 오류가 발생했습니다.'
      })
      setTimeout(() => setSaveMessage(null), 5000)
    } finally {
      setIsSaving(false)
    }
  }

  if (!translatedText) return null
  return (
    <div className="result">
      <div className="result-header">
        <h2>번역 결과</h2>
        <button onClick={onDownload} disabled={!canDownload}>
          엑셀로 다운로드
        </button>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
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
        <div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 600, color: '#000000' }}>
            직접 번역
          </h3>
          <textarea
            value={userTranslation}
            onChange={(e) => onUserTranslationChange(e.target.value)}
            placeholder="원문을 보고 직접 번역을 작성해보세요."
            style={{
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
              height: '600px',
              minHeight: '600px',
              maxHeight: '600px',
              overflowY: 'auto',
              width: '100%',
              boxSizing: 'border-box',
              resize: 'vertical',
              fontFamily: 'inherit',
              marginBottom: '12px',
            }}
          />
          {/* 저장 버튼 */}
          <button
            onClick={handleSave}
            disabled={isSaving || !originalText.trim()}
            style={{
              width: '100%',
              padding: '12px 24px',
              backgroundColor: isSaving ? '#9ca3af' : '#138577',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: isSaving || !originalText.trim() ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!isSaving && originalText.trim()) {
                e.currentTarget.style.backgroundColor = '#0f766e'
              }
            }}
            onMouseLeave={(e) => {
              if (!isSaving && originalText.trim()) {
                e.currentTarget.style.backgroundColor = '#138577'
              }
            }}
          >
            {isSaving ? '저장 중...' : '💾 번역 저장하기'}
          </button>
          {/* 저장 메시지 */}
          {saveMessage && (
            <div
              style={{
                marginTop: '8px',
                padding: '8px 12px',
                borderRadius: '6px',
                backgroundColor: saveMessage.type === 'success' ? '#d1fae5' : '#fee2e2',
                color: saveMessage.type === 'success' ? '#065f46' : '#991b1b',
                fontSize: '13px',
                fontWeight: 500,
              }}
            >
              {saveMessage.type === 'success' ? '✓ ' : '✗ '}
              {saveMessage.text}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}



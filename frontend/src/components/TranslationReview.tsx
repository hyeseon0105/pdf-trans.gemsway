import type { ReviewData } from '../api'

type Props = {
  review: ReviewData
}

export function TranslationReview({ review }: Props) {
  const { results, summary } = review

  const getStatusColor = (status: string) => {
    if (status === 'ok') return '#10b981' // green
    if (status.includes('⚠️')) return '#f59e0b' // amber
    if (status.includes('❌')) return '#ef4444' // red
    return '#6b7280' // gray
  }

  const getStatusIcon = (status: string) => {
    if (status === 'ok') return '✓'
    if (status.includes('⚠️')) return '⚠️'
    if (status.includes('❌')) return '❌'
    return '?'
  }

  const issues = results.filter(r => r.status !== 'ok')
  const hasIssues = issues.length > 0

  return (
    <div style={{
      marginTop: '24px',
      padding: '20px',
      backgroundColor: '#f9fafb',
      borderRadius: '12px',
      border: '1px solid #e5e7eb'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
          번역 검수 결과
        </h3>
        <div style={{
          padding: '6px 12px',
          borderRadius: '6px',
          backgroundColor: summary.accuracy_percent >= 80 ? '#d1fae5' : 
                          summary.accuracy_percent >= 60 ? '#fef3c7' : '#fee2e2',
          color: summary.accuracy_percent >= 80 ? '#065f46' : 
                 summary.accuracy_percent >= 60 ? '#92400e' : '#991b1b',
          fontWeight: 600,
          fontSize: '14px'
        }}>
          정확도: {summary.accuracy_percent}%
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '12px',
        marginBottom: '20px'
      }}>
        <div style={{ padding: '12px', backgroundColor: 'white', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>전체 문단</div>
          <div style={{ fontSize: '20px', fontWeight: 700 }}>{summary.total_paragraphs}</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: 'white', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>정상</div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: '#10b981' }}>{summary.ok_count}</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: 'white', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>불일치</div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: '#f59e0b' }}>{summary.warning_count}</div>
        </div>
        <div style={{ padding: '12px', backgroundColor: 'white', borderRadius: '8px' }}>
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>미번역</div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: '#ef4444' }}>{summary.missing_count}</div>
        </div>
      </div>

      {hasIssues && (
        <div>
          <h4 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: 600 }}>
            문제 항목 ({issues.length}개)
          </h4>
          <div style={{
            maxHeight: '400px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
            {issues.map((item, idx) => (
              <div
                key={idx}
                style={{
                  padding: '16px',
                  backgroundColor: 'white',
                  borderRadius: '8px',
                  border: `1px solid ${getStatusColor(item.status)}`,
                  borderLeftWidth: '4px'
                }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '12px'
                }}>
                  <span style={{ fontSize: '18px' }}>{getStatusIcon(item.status)}</span>
                  <span style={{
                    fontWeight: 600,
                    color: getStatusColor(item.status),
                    fontSize: '14px'
                  }}>
                    {item.status}
                  </span>
                  {item.similarity > 0 && (
                    <span style={{ fontSize: '12px', color: '#6b7280' }}>
                      (유사도: {(item.similarity * 100).toFixed(1)}%)
                    </span>
                  )}
                </div>
                
                {item.english && (
                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>원문:</div>
                    <div style={{
                      padding: '8px',
                      backgroundColor: '#f3f4f6',
                      borderRadius: '4px',
                      fontSize: '13px',
                      lineHeight: '1.5'
                    }}>
                      {item.english}
                    </div>
                  </div>
                )}
                
                {item.korean && (
                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>번역문:</div>
                    <div style={{
                      padding: '8px',
                      backgroundColor: '#f3f4f6',
                      borderRadius: '4px',
                      fontSize: '13px',
                      lineHeight: '1.5'
                    }}>
                      {item.korean}
                    </div>
                  </div>
                )}
                
                {item.suggestion && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>수정 제안:</div>
                    <div style={{
                      padding: '8px',
                      backgroundColor: '#fef3c7',
                      borderRadius: '4px',
                      fontSize: '13px',
                      lineHeight: '1.5',
                      border: '1px solid #fbbf24'
                    }}>
                      {item.suggestion}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasIssues && (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          color: '#10b981',
          backgroundColor: 'white',
          borderRadius: '8px'
        }}>
          ✓ 모든 번역이 정확합니다!
        </div>
      )}
    </div>
  )
}


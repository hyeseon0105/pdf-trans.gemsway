import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { LayoutPage } from '../api'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'

// pdf.js: bundle worker locally to avoid CORS
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
// pdf.js v4 + Vite: import as actual Web Worker (module worker)
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - Vite query parameter typing
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'
// create worker instance and pass directly
// eslint-disable-next-line new-cap
const pdfWorker: Worker = new (PdfWorker as unknown as { new (): Worker })()
GlobalWorkerOptions.workerPort = pdfWorker

type Props = {
  pdfUrl: string
  pages: LayoutPage[] | undefined
}

export type DesignPreviewHandle = {
  exportPdf: (filename: string) => Promise<void>
}

export const DesignPreview = forwardRef<DesignPreviewHandle, Props>(function DesignPreview(
  { pdfUrl, pages },
  ref
) {
  const [numPages, setNumPages] = useState<number>(0)
  const [rendered, setRendered] = useState<boolean>(false)
  const pageContainersRef = useRef<HTMLDivElement[]>([])

  // ensure array length
  if (pageContainersRef.current.length !== numPages) {
    pageContainersRef.current = Array.from({ length: numPages })
  }

  useImperativeHandle(ref, () => ({
    async exportPdf(filename: string) {
      // capture each page container (canvas + overlay)
      const doc = new jsPDF({ unit: 'pt', format: 'a4' })
      let isFirst = true
      for (let i = 0; i < pageContainersRef.current.length; i++) {
        const el = pageContainersRef.current[i]
        if (!el) continue
        const canvas = await html2canvas(el, {
          scale: 2,
          backgroundColor: '#ffffff',
          useCORS: true,
        })
        const imgData = canvas.toDataURL('image/jpeg', 0.95)
        // convert px to pt (assuming 96dpi): 1px ≈ 0.75pt
        const wPt = canvas.width * 0.75
        const hPt = canvas.height * 0.75
        if (isFirst) {
          doc.deletePage(1)
          isFirst = false
        }
        doc.addPage([wPt, hPt] as any)
        doc.addImage(imgData, 'JPEG', 0, 0, wPt, hPt)
      }
      if (isFirst) {
        // nothing rendered, create empty page
        doc.text('Empty', 40, 40)
      }
      doc.save(filename)
    },
  }))

  useEffect(() => {
    let cancelled = false
    async function run() {
      setRendered(false)
      const loadingTask = getDocument({ url: pdfUrl })
      const pdf = await loadingTask.promise
      if (cancelled) return
      setNumPages(pdf.numPages)
      // render pages sequentially
      for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
        const page = await pdf.getPage(pageNum)
        const container = pageContainersRef.current[pageNum - 1]
        if (!container) continue
        // scale based on desired width (fit to container width)
        const viewport = page.getViewport({ scale: 1.5 })
        // prepare canvas
        let canvas = container.querySelector('canvas') as HTMLCanvasElement | null
        if (!canvas) {
          canvas = document.createElement('canvas')
          canvas.style.display = 'block'
          container.appendChild(canvas)
        }
        const ctx = canvas.getContext('2d')!
        canvas.width = viewport.width
        canvas.height = viewport.height
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        // render page
        await page.render({ canvasContext: ctx, viewport }).promise
        // overlay
        let overlay = container.querySelector('.overlay') as HTMLDivElement | null
        if (!overlay) {
          overlay = document.createElement('div')
          overlay.className = 'overlay'
          overlay.style.position = 'absolute'
          overlay.style.left = '0'
          overlay.style.top = '0'
          overlay.style.width = `${viewport.width}px`
          overlay.style.height = `${viewport.height}px`
          overlay.style.pointerEvents = 'none'
          container.appendChild(overlay)
        } else {
          overlay.innerHTML = ''
          overlay.style.width = `${viewport.width}px`
          overlay.style.height = `${viewport.height}px`
        }
        // place blocks if provided
        const pageLayout = pages?.[pageNum - 1]
        if (pageLayout) {
          const scaleX = viewport.width / pageLayout.width
          const scaleY = viewport.height / pageLayout.height
          for (const b of pageLayout.blocks) {
            const [x0, y0, x1, y1] = b.bbox
            const bw = (x1 - x0) * scaleX
            const bh = (y1 - y0) * scaleY
            const left = x0 * scaleX
            const top = y0 * scaleY
            const minHeight = 36
            const effectiveHeight = Math.max(bh, minHeight)
            const topAdjusted = Math.max(0, top - (effectiveHeight - bh) / 2)
            const div = document.createElement('div')
            div.style.position = 'absolute'
            div.style.left = `${left}px`
            div.style.top = `${topAdjusted}px`
            div.style.width = `${bw}px`
            div.style.height = `${effectiveHeight}px`
            div.style.backgroundColor = '#ffffff' // 원본 텍스트를 가리는 흰색 배경
            div.style.color = '#000' // 기본 텍스트 색
            div.style.whiteSpace = 'pre-wrap'
            div.style.overflow = 'hidden'
            div.style.lineHeight = '1.2'
            div.style.pointerEvents = 'none'
            div.style.padding = '2px'
            const originalFont = Number((b as any).font_size) || 12
            const scaleFactor = Math.max(scaleX, scaleY)
            let baseFont = originalFont * scaleFactor
            if (originalFont >= 18) {
              baseFont = Math.max(baseFont, 24 * scaleFactor * 0.6)
            } else if (originalFont >= 14) {
              baseFont = Math.max(baseFont, 18 * scaleFactor * 0.6)
            } else {
              baseFont = Math.max(baseFont, 14 * scaleFactor * 0.6)
            }
            baseFont += 4 * scaleFactor
            div.dataset.baseFont = String(Math.max(14, Math.min(baseFont, 46)))
            div.textContent = (b as any).translated_text || b.text || ''
            overlay.appendChild(div)
            fitText(div)
          }
        }
      }
      if (!cancelled) setRendered(true)
    }
    run()
    return () => {
      cancelled = true
    }
  }, [pdfUrl, pages])

  return (
    <div className="design-preview">
      {Array.from({ length: numPages }).map((_, i) => (
        <div
          key={i}
          ref={(el) => {
            if (el) pageContainersRef.current[i] = el
          }}
          style={{
            position: 'relative',
            margin: '16px auto',
            boxShadow: '0 0 8px rgba(0,0,0,0.15)',
            background: '#fff',
            width: 'fit-content',
          }}
        />
      ))}
      {!rendered && <p>원본 디자인을 렌더링 중입니다...</p>}
    </div>
  )
})

function fitText(el: HTMLDivElement) {
  const maxW = el.clientWidth
  const maxH = el.clientHeight
  if (maxW <= 0 || maxH <= 0) return
  const baseSizeAttr = parseFloat(el.dataset.baseFont || '16')
  const baseSize = Number.isFinite(baseSizeAttr) ? baseSizeAttr : 16
  const minSize = 6
  let fontSize = Math.min(baseSize, Math.floor(maxH * 0.9))
  if (fontSize < minSize) {
    fontSize = minSize
  }
  el.style.fontSize = `${fontSize}px`
  // 줄 간격도 폰트와 맞춤
  el.style.lineHeight = '1.2'
  // 줄이 넘치면 감소
  const fits = () => el.scrollWidth <= maxW + 1 && el.scrollHeight <= maxH + 1
  // 빠른 이분 탐색으로 수렴
  let lo = minSize
  let hi = fontSize
  if (!fits()) {
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2)
      el.style.fontSize = `${mid}px`
      if (fits()) {
        // 더 키워볼 수 있음
        lo = mid + 1
      } else {
        hi = mid
      }
    }
    el.style.fontSize = `${Math.max(minSize, hi - 1)}px`
  }
}



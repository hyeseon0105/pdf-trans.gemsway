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
  bgImages?: string[]
  previewId?: string
}

export type DesignPreviewHandle = {
  exportPdf: (filename: string) => Promise<void>
}

export const DesignPreview = forwardRef<DesignPreviewHandle, Props>(function DesignPreview(
  { pdfUrl, pages, bgImages, previewId },
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
      console.log('DesignPreview useEffect triggered', { pdfUrl, pagesCount: pages?.length, bgImagesCount: bgImages?.length })

      // Image mode (server-side inpainted backgrounds)
      if (bgImages && bgImages.length > 0) {
        console.log('Using inpainted preview images:', bgImages.length, 'pages', bgImages)
        setNumPages(bgImages.length)
        // Wait for React to render containers
        await new Promise(resolve => setTimeout(resolve, 50))
        if (cancelled) return
        
        const loadPromises: Promise<void>[] = []
        for (let pageNum = 1; pageNum <= bgImages.length; pageNum++) {
          const container = pageContainersRef.current[pageNum - 1]
          if (!container) {
            console.warn(`Container for page ${pageNum} not found`)
            continue
          }
          container.innerHTML = ''
          const imgUrl = bgImages[pageNum - 1]
          console.log(`Loading image for page ${pageNum}:`, imgUrl)
          
          // load image
          const loadPromise = new Promise<void>((resolve, reject) => {
            const img = new Image()
            img.crossOrigin = 'anonymous'
            img.onload = () => {
              if (cancelled) {
                resolve()
                return
              }
              try {
                const width = img.naturalWidth
                const height = img.naturalHeight
                console.log(`Image loaded for page ${pageNum}:`, width, 'x', height)
                // add image canvas
                const canvas = document.createElement('canvas')
                canvas.width = width
                canvas.height = height
                canvas.style.display = 'block'
                canvas.style.width = `${width}px`
                canvas.style.height = `${height}px`
                canvas.style.marginLeft = '0'
                canvas.style.marginRight = '0'
                const ctx = canvas.getContext('2d')!
                ctx.drawImage(img, 0, 0)
                container.appendChild(canvas)
                // overlay
                let overlay = document.createElement('div')
                overlay.className = 'overlay'
                overlay.style.position = 'absolute'
                overlay.style.left = '0'
                overlay.style.top = '0'
                overlay.style.width = `${width}px`
                overlay.style.height = `${height}px`
                overlay.style.pointerEvents = 'none'
                overlay.style.zIndex = '2'
                overlay.style.backgroundColor = 'transparent'
                overlay.style.background = 'none'
                overlay.style.border = 'none'
                overlay.style.boxShadow = 'none'
                container.appendChild(overlay)

                // Render Korean text on overlay (server already rendered it, but overlay ensures all text is visible)
                const pageLayout = pages?.[pageNum - 1]
                if (pageLayout) {
                  const scaleX = width / pageLayout.width
                  const scaleY = height / pageLayout.height
                  
                  // Sort blocks by y position (top to bottom) to handle overlaps
                  const sortedBlocks = [...pageLayout.blocks]
                    .map((b, idx) => ({ block: b, originalIdx: idx }))
                    .sort((a, b) => {
                      const aY = a.block.bbox[1]
                      const bY = b.block.bbox[1]
                      if (Math.abs(aY - bY) < 5) {
                        // If y is similar, sort by x
                        return a.block.bbox[0] - b.block.bbox[0]
                      }
                      return aY - bY
                    })
                  
                  // Track rendered text areas to avoid overlaps
                  const renderedAreas: Array<{ x0: number, y0: number, x1: number, y1: number }> = []
                  const minBlockSpacing = 5 // Minimum spacing between blocks (pixels)
                  
                  for (const { block: b, originalIdx } of sortedBlocks) {
                    const [x0, y0, x1, y1] = b.bbox
                    const bw = (x1 - x0) * scaleX
                    const bh = (y1 - y0) * scaleY
                    const left = x0 * scaleX
                    let top = y0 * scaleY
                    
                    // 텍스트 블록이 비정상적으로 크면 (페이지의 30% 이상) 건너뛰기
                    const blockArea = bw * bh
                    const pageArea = width * height
                    if (blockArea > pageArea * 0.3) {
                      continue
                    }
                    
                    // 텍스트가 없거나 너무 짧으면 건너뛰기
                    const text = (b as any).translated_text || b.text || ''
                    if (!text.trim() || text.trim().length < 2) {
                      continue
                    }
                    
                    // 텍스트 블록 영역의 배경이 이미지인지 확인
                    try {
                      const sampleLeft = Math.max(0, Math.floor(left))
                      const sampleTop = Math.max(0, Math.floor(top))
                      const sampleWidth = Math.min(width - sampleLeft, Math.ceil(bw))
                      const sampleHeight = Math.min(height - sampleTop, Math.ceil(bh))
                      
                      if (sampleWidth > 0 && sampleHeight > 0) {
                        const imgData = ctx.getImageData(sampleLeft, sampleTop, sampleWidth, sampleHeight)
                        const data = imgData.data
                        
                        // RGB 값들의 분산도 계산
                        let rSum = 0, gSum = 0, bSum = 0
                        let rSum2 = 0, gSum2 = 0, bSum2 = 0
                        let rMin = 255, gMin = 255, bMin = 255
                        let rMax = 0, gMax = 0, bMax = 0
                        const pixelCount = data.length / 4
                        
                        for (let i = 0; i < data.length; i += 4) {
                          const r = data[i]
                          const g = data[i + 1]
                          const b = data[i + 2]
                          rSum += r
                          gSum += g
                          bSum += b
                          rSum2 += r * r
                          gSum2 += g * g
                          bSum2 += b * b
                          rMin = Math.min(rMin, r)
                          gMin = Math.min(gMin, g)
                          bMin = Math.min(bMin, b)
                          rMax = Math.max(rMax, r)
                          gMax = Math.max(gMax, g)
                          bMax = Math.max(bMax, b)
                        }
                        
                        const rMean = rSum / pixelCount
                        const gMean = gSum / pixelCount
                        const bMean = bSum / pixelCount
                        const rVar = (rSum2 / pixelCount) - (rMean * rMean)
                        const gVar = (gSum2 / pixelCount) - (gMean * gMean)
                        const bVar = (bSum2 / pixelCount) - (bMean * bMean)
                        const avgVariance = (rVar + gVar + bVar) / 3
                        
                        // 밝기 범위 계산
                        const brightnessRange = Math.max(rMax - rMin, gMax - gMin, bMax - bMin)
                        
                        // 이미지 영역 판단 조건
                        const avgBrightness = (rMean + gMean + bMean) / 3
                        const isDark = avgBrightness < 120
                        const isComplex = avgVariance > 150 || brightnessRange > 80 || (isDark && avgVariance > 50) || brightnessRange > 60
                        
                        if (isComplex) {
                          console.log(`Skipping text block on image background (variance: ${avgVariance.toFixed(1)}, brightnessRange: ${brightnessRange}, avgBrightness: ${avgBrightness.toFixed(1)})`)
                          continue
                        }
                      }
                    } catch (err) {
                      console.warn('Failed to analyze background for text block:', err)
                    }
                    
                    // Check for overlaps with previously rendered blocks
                    // Adjust top if this block overlaps with previous blocks
                    for (const prevArea of renderedAreas) {
                      // Check if blocks overlap horizontally
                      const horizontalOverlap = !(left + bw < prevArea.x0 || left > prevArea.x1)
                      if (horizontalOverlap) {
                        // Check if this block starts too close to previous block's end
                        if (top < prevArea.y1 + minBlockSpacing) {
                          // Adjust top to add spacing
                          top = prevArea.y1 + minBlockSpacing
                        }
                      }
                    }
                    
                    // 텍스트가 원본 bbox 영역을 절대 벗어나지 않도록 제한
                    // 원본 위치와 크기를 정확히 유지
                    const div = document.createElement('div')
                    div.style.position = 'absolute'
                    // 원본 bbox 위치를 정확히 유지 (절대 변경하지 않음)
                    div.style.left = `${Math.round(left)}px`
                    div.style.top = `${Math.round(top)}px`
                    // 원본 bbox 크기를 정확히 유지 (절대 변경하지 않음)
                    div.style.width = `${Math.round(bw)}px`
                    div.style.height = `${Math.round(bh)}px`
                    div.style.maxWidth = `${Math.round(bw)}px`
                    div.style.maxHeight = `${Math.round(bh)}px`
                    div.style.background = 'transparent'
                    div.style.backgroundColor = 'transparent'
                    div.style.color = '#000'
                    div.style.whiteSpace = 'pre-wrap'
                    div.style.overflow = 'hidden'
                    div.style.lineHeight = '1.6'  // 60% spacing to prevent text overlap
                    div.style.pointerEvents = 'none'
                    // Minimize padding to maximize horizontal space and reduce line breaks
                    div.style.padding = '0'
                    div.style.margin = '0'
                    div.style.boxSizing = 'border-box'
                    div.style.textAlign = 'left'
                    div.style.verticalAlign = 'top'
                    div.style.wordBreak = 'break-word'
                    div.style.wordWrap = 'break-word'
                    div.style.overflowWrap = 'break-word'
                    
                    // 원본 폰트 크기를 정확히 스케일링 - 원본 크기를 더 잘 유지
                    const originalFont = Number((b as any).font_size) || 12
                    const scaleFactor = Math.min(scaleX, scaleY)
                    let baseFont = originalFont * scaleFactor
                    // 최소 폰트 크기를 높여서 읽기 좋게 (10px), 원본 크기의 50% 이상 유지
                    // 가로 공간을 더 활용하기 위해 폭 기준 계산을 조정 (bw / 10 -> bw / 12로 변경하여 더 넓게)
                    const minFontSize = Math.max(10, originalFont * scaleFactor * 0.5)
                    baseFont = Math.max(minFontSize, Math.min(baseFont, Math.min(bh * 0.85, bw / 12)))
                    div.dataset.baseFont = String(Math.round(baseFont))
                    
                    // 원본 텍스트 시작점을 사용하여 정렬 (있는 경우)
                    // 최소한의 padding만 사용하여 가로 공간 최대화
                    const textStartX = (b as any).text_start_x
                    if (textStartX !== undefined) {
                      const textStartOffset = (textStartX * scaleX) - left
                      div.style.paddingLeft = `${Math.max(0, Math.min(textStartOffset, 2))}px`  // 최대 2px로 제한
                    } else {
                      div.style.paddingLeft = '1px'  // 최소한의 padding
                    }
                    div.style.paddingRight = '1px'  // 최소한의 padding
                    
                    div.textContent = (b as any).translated_text || b.text || ''
                    overlay.appendChild(div)
                    
                    // 텍스트가 bbox 안에 맞도록 폰트 크기 조정
                    fitText(div)
                    
                    // Record the actual rendered area for overlap detection
                    // Measure actual height after fitText (synchronous)
                    const rect = div.getBoundingClientRect()
                    const overlayRect = overlay.getBoundingClientRect()
                    const actualTop = rect.top - overlayRect.top
                    const actualHeight = rect.height
                    const actualLeft = rect.left - overlayRect.left
                    const actualWidth = rect.width
                    
                    renderedAreas.push({
                      x0: actualLeft,
                      y0: actualTop,
                      x1: actualLeft + actualWidth,
                      y1: actualTop + actualHeight + minBlockSpacing // Add spacing for next block
                    })
                  }
                }
                resolve()
              } catch (err) {
                console.error(`Error rendering page ${pageNum}:`, err)
                reject(err)
              }
            }
            img.onerror = (err) => {
              console.error(`Failed to load image for page ${pageNum}:`, imgUrl, err)
              reject(new Error(`Failed to load image: ${imgUrl}`))
            }
            img.src = imgUrl
          })
          loadPromises.push(loadPromise)
        }
        
        try {
          await Promise.all(loadPromises)
          if (!cancelled) {
            console.log('All preview images loaded successfully')
            setRendered(true)
          }
        } catch (err) {
          console.error('Error loading preview images:', err)
          if (!cancelled) setRendered(true)
        }
        return
      }

      // PDF canvas mode (fallback)
      console.log('Preview images not available, falling back to PDF canvas mode', { pdfUrl })
      if (!pdfUrl) {
        console.error('PDF URL is missing!')
        return
      }
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
          overlay.style.backgroundColor = 'transparent'
          overlay.style.background = 'none'
          container.appendChild(overlay)
        } else {
          overlay.innerHTML = ''
          overlay.style.width = `${viewport.width}px`
          overlay.style.height = `${viewport.height}px`
          overlay.style.backgroundColor = 'transparent'
          overlay.style.background = 'none'
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
            div.style.backgroundColor = 'transparent' // 배경 투명
            div.style.background = 'none'
            div.style.color = '#000' // 기본 텍스트 색
            div.style.whiteSpace = 'pre-wrap'
            div.style.overflow = 'hidden'
            div.style.lineHeight = '1.2'
            div.style.pointerEvents = 'none'
            div.style.padding = '0' // padding 제거
            div.style.margin = '0'
            div.style.border = 'none'
            div.style.boxShadow = 'none'
            const originalFont = Number((b as any).font_size) || 12
            const scaleFactor = Math.min(scaleX, scaleY)  // Use smaller scale to preserve size better
            let baseFont = originalFont * scaleFactor
            // 최소 폰트 크기를 높여서 읽기 좋게 (10px), 원본 크기의 50% 이상 유지
            const minFontSize = Math.max(10, originalFont * scaleFactor * 0.5)
            // 원본 크기를 더 잘 유지하도록 조정
            baseFont = Math.max(minFontSize, Math.min(baseFont, Math.min(effectiveHeight * 0.85, bw / 8)))
            div.dataset.baseFont = String(Math.round(baseFont))
            
            // 원본 텍스트 시작점을 사용하여 정렬 (있는 경우)
            const textStartX = (b as any).text_start_x
            if (textStartX !== undefined) {
              const textStartOffset = (textStartX * scaleX) - left
              div.style.paddingLeft = `${Math.max(0, textStartOffset)}px`
            }
            
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
  }, [pdfUrl, pages, bgImages, previewId])

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
            background: 'transparent',
            backgroundColor: 'transparent',
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
  // 최소 폰트 크기를 높여서 읽기 좋게 (10px)
  const minSize = 10
  // 초기 폰트 크기를 원본에 가깝게 유지
  let fontSize = Math.min(baseSize, Math.floor(maxH * 0.9))
  // 최소 크기는 원본의 50% 이상
  const minPreservedSize = Math.max(minSize, baseSize * 0.5)
  if (fontSize < minPreservedSize) {
    fontSize = minPreservedSize
  }
  el.style.fontSize = `${fontSize}px`
  // 줄 간격도 폰트와 맞춤 - 겹침 방지를 위해 더 큰 간격 사용
  el.style.lineHeight = '1.6'  // 60% spacing to prevent descenders from overlapping with ascenders
  // 텍스트가 bbox 안에 완전히 들어가는지 확인
  // 여유 공간을 두어 텍스트가 잘리지 않도록
  const fits = () => {
    // 약간의 여유를 두어 텍스트가 잘리지 않도록
    const widthFits = el.scrollWidth <= maxW + 2
    const heightFits = el.scrollHeight <= maxH + 2
    return widthFits && heightFits
  }
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
    // 안전하게 한 단계 더 작게 설정하여 텍스트가 잘리지 않도록
    el.style.fontSize = `${Math.max(minSize, hi - 2)}px`
    
    // 최종 확인 - 여전히 넘치면 더 줄임
    if (!fits()) {
      let safeSize = Math.max(minSize, hi - 3)
      while (safeSize >= minSize && !fits()) {
        el.style.fontSize = `${safeSize}px`
        safeSize--
      }
    }
  }
}



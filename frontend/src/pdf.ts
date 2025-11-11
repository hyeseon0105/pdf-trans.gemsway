import { jsPDF } from 'jspdf'

export function generatePdfFromText(text: string, outputFileName: string) {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const pageWidth = doc.internal.pageSize.getWidth()
  const pageHeight = doc.internal.pageSize.getHeight()
  const margin = 48 // 48pt ≈ 17mm
  const usableWidth = pageWidth - margin * 2

  doc.setFont('Helvetica', 'normal')
  doc.setFontSize(12)

  let cursorY = margin

  const addPageIfNeeded = (neededHeight: number) => {
    if (cursorY + neededHeight > pageHeight - margin) {
      doc.addPage()
      doc.setFont('Helvetica', 'normal')
      doc.setFontSize(12)
      cursorY = margin
    }
  }

  const paragraphs = text.split(/\n{2,}/g)
  paragraphs.forEach((para, idx) => {
    const lines = doc.splitTextToSize(para, usableWidth)
    const blockHeight = lines.length * 16 // 16pt line height
    addPageIfNeeded(blockHeight)
    doc.text(lines, margin, cursorY, { align: 'left', baseline: 'top' })
    cursorY += blockHeight

    // space between paragraphs
    const spacer = 12
    if (idx < paragraphs.length - 1) {
      addPageIfNeeded(spacer)
      cursorY += spacer
    }
  })

  doc.save(outputFileName)
}



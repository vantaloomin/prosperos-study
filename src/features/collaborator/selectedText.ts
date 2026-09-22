import type { TextSelection } from '../textEdits/types'
import { wholeText } from '../textEdits/types'

// MessageCard renders literal paragraphs separated by two source newlines.
// Convert DOM endpoints to source offsets; never search for repeated wording.
export function selectedProse(root: HTMLElement | null, text: string): TextSelection {
  const selection = window.getSelection()
  if (!root || !selection?.rangeCount || selection.isCollapsed) return wholeText(text)
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return wholeText(text)
  const start = sourceOffset(root, range.startContainer, range.startOffset)
  const end = sourceOffset(root, range.endContainer, range.endOffset)
  if (start === null || end === null) throw new Error('Select text within this passage, then send it again.')
  return { start, end, text: text.slice(start, end) }
}

function sourceOffset(root: HTMLElement, node: Node, offset: number): number | null {
  if (node === root) { const children = Array.from(root.children).slice(0, offset); return children.reduce((sum, item) => sum + (item.textContent?.length ?? 0), 0) + Math.min(offset, root.children.length - 1) * 2 }
  const paragraphs = Array.from(root.children)
  const paragraph = paragraphs.find(item => item.contains(node))
  if (!paragraph) return null
  const prefix = document.createRange(); prefix.selectNodeContents(paragraph); prefix.setEnd(node, offset)
  const previous = paragraphs.slice(0, paragraphs.indexOf(paragraph)).reduce((sum, item) => sum + (item.textContent?.length ?? 0) + 2, 0)
  return previous + prefix.toString().length
}

export function selectedInline(root: HTMLElement | null, text: string): TextSelection {
  const selection = window.getSelection()
  if (!root || !selection?.rangeCount || selection.isCollapsed) return wholeText(text)
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return wholeText(text)
  const prefix = document.createRange(); prefix.selectNodeContents(root); prefix.setEnd(range.startContainer, range.startOffset)
  const start = prefix.toString().length, end = start + range.toString().length
  if (root.textContent !== text) throw new Error('This display differs from the source. Open the source passage before choosing a selection.')
  return { start, end, text: text.slice(start, end) }
}

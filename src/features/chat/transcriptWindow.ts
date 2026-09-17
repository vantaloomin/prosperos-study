import type { Message } from '../../types'
import type { ReadingPosition } from './readingPosition'

export function initialMessageIndex(messages: Pick<Message, 'id'>[], position: ReadingPosition | null) {
  if (!position || position.atEnd) return Math.max(0, messages.length - 1)
  const id = position.block?.split(':')[0]
  const index = messages.findIndex((message) => message.id === id)
  if (index >= 0) return index
  return Math.min(Math.max(0, messages.length - 1), Math.max(0, Math.floor(position.pixels / 300)))
}

export function findPassages(messages: Pick<Message, 'text'>[], query: string): number[] {
  const value = query.trim().toLocaleLowerCase()
  if (/^\d+$/.test(value)) {
    const index = Number(value) - 1
    return index >= 0 && index < messages.length ? [index] : []
  }
  const matches: number[] = []
  for (let index = 0; index < messages.length; index++) {
    if (!value || messages[index].text.toLocaleLowerCase().includes(value)) matches.push(index)
  }
  return matches
}

export function passagePosition(messageId: string): ReadingPosition {
  return { block: `${messageId}:header`, offset: 0, fraction: 0, pixels: 0, atEnd: false }
}

export function hasReadingAnchor(messages: Pick<Message, 'id' | 'text'>[], block: string) {
  const [id, part] = block.split(':')
  const message = messages.find((item) => item.id === id)
  if (!message) return false
  if (part === 'header') return true
  return /^p\d+$/.test(part) && Number(part.slice(1)) < message.text.split('\n\n').length
}

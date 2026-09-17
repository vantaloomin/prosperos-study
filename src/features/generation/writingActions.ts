import { createContext, useContext } from 'react'
import type { MessageReceipt } from './continuation'

export interface WritingActions { onSubmitted: (receipt: MessageReceipt) => Promise<void>; busy: boolean; error: string; canGenerate: boolean }
export const WritingContext = createContext<WritingActions | null>(null)
export function useWritingActions() {
  const context = useContext(WritingContext)
  if (!context) throw new Error('The composer needs a writing session.')
  return context
}

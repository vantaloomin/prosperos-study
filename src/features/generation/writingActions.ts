import { createContext, useContext, type ReactNode } from 'react'
import type { MessageReceipt } from './continuation'

export interface WritingActions {
  onSubmitted: (receipt: MessageReceipt) => Promise<void>; busy: boolean; error: string; canGenerate: boolean
  anchor: string | null; surface: ReactNode; recovery: ReactNode
}
export const WritingContext = createContext<WritingActions | null>(null)
export function useWritingActions() {
  const context = useContext(WritingContext)
  if (!context) throw new Error('The composer needs a writing session.')
  return context
}

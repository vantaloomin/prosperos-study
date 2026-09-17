import { useState } from 'react'
import type { Branch } from '../../types'

export function usePreparedBeat(branch: Branch) {
  const [skippedBeat, setSkippedBeat] = useState('')
  const prepared = branch.mechanics.pending
  const usePrepared = !!prepared && !prepared.stale && skippedBeat !== prepared.id
  return { prepared, usePrepared, setSkippedBeat }
}

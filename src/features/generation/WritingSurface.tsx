import { useWritingActions } from './writingActions'

export function WritingSurface({ after }: { after: string | null }) {
  const { anchor, surface } = useWritingActions()
  return anchor === after ? surface : null
}

export function WritingRecovery() {
  return useWritingActions().recovery
}

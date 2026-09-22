import { lazy, Suspense, useRef, useState } from 'react'
import { Loading } from '../../components/Feedback'
import type { RecipeSelection } from './recipeRunTypes'

const RecipeDialog = lazy(() => import('./RecipeDialog').then(module => ({ default: module.RecipeDialog })))

export function RecipeLauncher({ selection, onBranch }: { selection: RecipeSelection; onBranch: (id: string) => void }) {
  const [initial, setInitial] = useState<RecipeSelection | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  return <><button ref={trigger} className="button" onClick={() => setInitial(structuredClone(selection))}>Run recipe</button>{initial && <Suspense fallback={<Loading label="Opening recipe setup…" />}><RecipeDialog initial={initial} onClose={() => setInitial(null)} onBranch={onBranch} focusOnClose={() => trigger.current} /></Suspense>}</>
}

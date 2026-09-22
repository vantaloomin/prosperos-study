import { lazy, Suspense, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { recipeStatus, type RecipeHistoryItem } from './recipeRunTypes'
import './recipeRuns.css'

const RecipeDialog = lazy(() => import('./RecipeDialog').then(module => ({ default: module.RecipeDialog })))

export function RecipeHistory({ branchId, onBranch }: { branchId: string; onBranch: (id: string) => void }) {
  const [id, setId] = useState('')
  const [search, setSearch] = useState('')
  const trigger = useRef<HTMLButtonElement | null>(null)
  const query = useQuery({ queryKey: ['recipe-history', branchId], queryFn: () => api<RecipeHistoryItem[]>(`/branches/${branchId}/recipe-runs`), refetchInterval: 2500 })
  const matches = query.data?.filter(item => item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())) ?? []
  return <section className="form-stack"><h3>Saved recipe runs</h3><p className="subtle">Select text in the composer or a supported text editor and choose Run recipe. Return here to inspect or continue any saved run on this telling. The latest 100 runs are shown.</p><label className="field"><span>Find a saved recipe run</span><input aria-label="Find a saved recipe run" value={search} onChange={event => setSearch(event.target.value)} /></label><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Finding saved recipe runs…" />}<div className="recipe-history">{matches.map(item => <button className="button quiet" key={item.id} onClick={event => { trigger.current = event.currentTarget; setId(item.id) }}><span>{item.name} · {new Date(item.created_at).toLocaleString()}<br /><small>{recipeStatus[item.status]} · {item.revision} started steps</small></span></button>)}</div>{query.isSuccess && !matches.length && <p className="subtle">No matching recipe runs.</p>}{id && <Suspense fallback={<Loading label="Opening the recipe…" />}><RecipeDialog runId={id} onClose={() => setId('')} onBranch={onBranch} focusOnClose={() => trigger.current} /></Suspense>}</section>
}

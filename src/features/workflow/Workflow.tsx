import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readyProfiles } from '../models/profileReadiness'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import type { ModelProfile, ProfileList } from '../models/types'
import { PromptEditor, type Prompt } from '../prompts/Prompts'
import { ScenePlans } from '../scenes/ScenePlans'
import { ReviewSetup } from './ReviewSetup'
import { ReviewResults } from './ReviewResults'
import { RoutingEditor } from './RoutingEditor'
import type { ReviewHistoryItem, Routing } from './types'

type ReviewHistory = ReviewHistoryItem[]

function SavedReviews({ history, reviewId, onSelect, branch, routing }: { history: ReviewHistory; reviewId: string; onSelect: (id: string) => void; branch: Branch; routing: Routing }) {
  return <><div className="review-history">{history.map((review, index) => <button className="button quiet" key={review.id} aria-pressed={reviewId === review.id} onClick={() => onSelect(review.id)}>{review.scene ? `Draft · ${review.scene.title}` : `Passage review ${history.length - index}`} · {new Date(review.created_at).toLocaleString()}</button>)}{!history.length && <p className="subtle">No specialist reviews have been requested on this branch.</p>}</div>{reviewId && <ReviewResults key={reviewId} id={reviewId} branch={branch} steps={routing.steps} />}</>
}

function WorkflowContent({ tab, branch, routing, profiles, history, reviewId, onStarted, onSelect, onPrompt, onBranch }: {
  tab: string; branch: Branch; routing: Routing; profiles: ModelProfile[]; history: ReviewHistory; reviewId: string
  onStarted: (id: string) => void; onSelect: (id: string) => void; onPrompt: (key: string) => void
  onBranch: (id: string) => void
}) {
  if (tab === 'scenes') return <ScenePlans branch={branch} profiles={profiles} routing={routing} onBranch={onBranch} />
  if (tab === 'review') return <ReviewSetup key={branch.head_id} branch={branch} routing={routing} profiles={profiles} onStarted={onStarted} />
  if (tab === 'routing') return <RoutingEditor storyId={branch.story_id} data={routing} profiles={profiles} onPrompt={onPrompt} />
  return <SavedReviews history={history} reviewId={reviewId} onSelect={onSelect} branch={branch} routing={routing} />
}

export function Workflow({ branch, onBranch }: { branch: Branch; onBranch: (id: string) => void }) {
  const routing = useQuery({ queryKey: ['workflow', branch.story_id], queryFn: () => api<Routing>(`/stories/${branch.story_id}/workflow`) })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const prompts = useQuery({ queryKey: ['prompts', branch.story_id], queryFn: () => api<Prompt[]>(`/prompts?story_id=${branch.story_id}`) })
  const history = useQuery({ queryKey: ['reviews', branch.id], queryFn: () => api<ReviewHistory>(`/branches/${branch.id}/reviews`) })
  const [tab, setTab] = useState('scenes')
  const [reviewId, setReviewId] = useState('')
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const tabs = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (document.activeElement === document.body || document.activeElement?.getAttribute('role') === 'dialog') tabs.current?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [tab])
  const start = (id: string) => { setReviewId(id); setTab('history') }
  const editPrompt = (key: string) => setPrompt(prompts.data?.find((item) => item.key === key) ?? null)
  const error = [routing, profiles, prompts, history].map((query) => query.error?.message).find(Boolean)
  return <><div className="dialog-body workflow-panel"><div ref={tabs} className="tabs workflow-tabs" aria-label="Story workflow views">{[['scenes', 'Plan a scene'], ['review', 'Review a passage'], ['routing', 'Models by step'], ['history', 'Saved reviews']].map(([key, label]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}</div>
    <ErrorNotice message={error} />
    {!routing.data || !profiles.data || !prompts.data ? <Loading label="Opening the workflow…" /> : <div className="workflow-content">
      <WorkflowContent tab={tab} branch={branch} routing={routing.data} profiles={profiles.data.profiles} history={history.data ?? []} reviewId={reviewId} onStarted={start} onSelect={setReviewId} onPrompt={editPrompt} onBranch={onBranch} />
    </div>}
  </div>{prompt && <PromptEditor prompt={prompt} storyId={branch.story_id} onClose={() => setPrompt(null)} />}</>
}

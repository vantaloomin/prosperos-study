import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import { PlanManager } from '../storyMemory/PlanManager'
import type { PlanView } from '../storyMemory/planTypes'

export function ContinuityMemory({ branch, onReadMessage }: { branch: Branch; onReadMessage: (messageId: string) => void }) {
  const query = useQuery({ queryKey: ['continuity', branch.id, branch.head_id, branch.revision], queryFn: () => api<PlanView>(`/branches/${branch.id}/plans`) })
  if (query.isPending) return <Loading label="Opening this path’s memory…" />
  return <>{query.data && <PlanManager key={branch.id} branchId={branch.id} storyId={branch.story_id} view={query.data} onReadMessage={onReadMessage} />}<span className="eyebrow">ACCEPTED ON THIS PATH</span><p className="subtle">Facts, knowledge and threads selected when accepting scenes. Shared Library material stays separate.</p><ErrorNotice message={query.error?.message} />
    {query.data?.entries.filter(item => !item.plan).map((item) => <details className="context-asset" key={item.id}><summary><span>{item.subject}<small>{item.kind} · {item.status}</small></span></summary><p>{item.text}</p><button className="text-button" onClick={() => onReadMessage(item.node_id)}>Read the source scene</button>{item.evidence.map((evidence, index) => <blockquote key={index}>{evidence.quote}</blockquote>)}</details>)}
    {!query.data?.entries.length && <p className="subtle">No structured continuity has been accepted on this path.</p>}
    {!!query.data?.commits.length && <div className="context-section"><span className="eyebrow">CONTINUITY HISTORY</span>{query.data.commits.map((commit) => <details className="context-asset" key={commit.id}><summary>{new Date(commit.created_at).toLocaleString()} · {commit.changes.length} changes</summary><p>{commit.summary || 'No structured summary was selected.'}</p>{commit.note && <p>{commit.note}</p>}{commit.changes.map(change => <p key={change.id}>{change.subject}: {change.plan?.status ?? change.action} · {change.text}</p>)}<button className="text-button" onClick={() => onReadMessage(commit.node_id)}>Read accepted scene</button></details>)}</div>}
  </>
}

import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import type { ContinuityView } from '../scenes/continuityTypes'

export function ContinuityMemory({ branch }: { branch: Branch }) {
  const query = useQuery({ queryKey: ['continuity', branch.id, branch.head_id], queryFn: () => api<ContinuityView>(`/branches/${branch.id}/continuity`) })
  if (query.isPending) return <Loading label="Opening this path’s memory…" />
  return <><span className="eyebrow">ACCEPTED ON THIS PATH</span><p className="subtle">Facts, knowledge and threads selected when accepting scenes. Shared Library material stays separate.</p><ErrorNotice message={query.error?.message} />
    {query.data?.entries.map((item) => <details className="context-asset" key={item.id}><summary><span>{item.subject}<small>{item.kind} · {item.status}</small></span></summary><p>{item.text}</p><a className="text-button" href={`#message-${item.node_id}`}>Read the source scene</a>{item.evidence.map((evidence, index) => <blockquote key={index}>{evidence.quote}</blockquote>)}</details>)}
    {!query.data?.entries.length && <p className="subtle">No structured continuity has been accepted on this path.</p>}
    {!!query.data?.commits.length && <div className="context-section"><span className="eyebrow">SCENE HISTORY</span>{query.data.commits.map((commit) => <details className="context-asset" key={commit.id}><summary>{new Date(commit.created_at).toLocaleString()} · {commit.changes.length} changes</summary><p>{commit.summary || 'No structured summary was selected.'}</p>{commit.note && <p>{commit.note}</p>}<a className="text-button" href={`#message-${commit.node_id}`}>Read accepted scene</a></details>)}</div>}
  </>
}

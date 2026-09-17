import type { SceneResult } from './types'
import type { Evidence, TriageItem } from './revisionTypes'

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return <>{evidence.map((item, index) => <div key={index}><blockquote>{item.quote}</blockquote><small>Source: {item.source_id}</small></div>)}</>
}

export function TriageText({ item }: { item: TriageItem }) {
  return <><h4>{item.id} · {item.disposition}</h4><p>{item.reason}</p>{item.action && <p><strong>Proposed action:</strong> {item.action}</p>}<EvidenceList evidence={item.evidence} /></>
}

export function RevisionArtifact({ result }: { result: SceneResult }) {
  return <div className="form-stack"><p>{result.summary}</p>{result.approach && <p className="subtle">Recommended approach: {result.approach}. The director still chooses the changes.</p>}{result.items?.map((item) => <article className="review-finding" key={item.id}><TriageText item={item} /><small>Findings: {item.finding_ids.join(', ')}</small></article>)}{result.verdict && <><strong>Verdict: {result.verdict}</strong><EvidenceList evidence={result.evidence ?? []} /><p>{result.smallest_fix}</p><p className="subtle">Selecting this verdict does not resolve the item or approve a change.</p></>}</div>
}

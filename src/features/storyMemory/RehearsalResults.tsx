import { useEffect, useRef } from 'react'
import type { Source } from './types'
import { conflictLabels, knowledgeLabels, viewpointLabel, type RehearsalDecision, type RehearsalItem, type RehearsalReport } from './rehearsalTypes'

export function RehearsalResults({ report, onDecisions }: { report: RehearsalReport; onDecisions: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: 'start' }) }, [report])
  return <section className="form-stack"><h3 tabIndex={-1} ref={heading}>Evidence for this rehearsal</h3><p>{report.query}</p>
    <p className="subtle">Snapshot at Story revision {report.boundary.revision}. Searched {report.source_count.toLocaleString()} eligible excerpts; showing {report.items.length}. Matches use wording and saved author descriptions. They do not prove a statement true or detect every contradiction.</p>
    {report.unavailable_decisions > 0 && <p role="status">{report.unavailable_decisions} author decision(s) need source review. Their grants are unavailable; retained does-not-know restrictions still apply to matching evidence.</p>}
    {!report.items.length && <p>No matching excerpt found. Try another name or phrase; this does not establish that an event never happened.</p>}
    {report.items.map(item => <EvidenceCard key={item.source.id} item={item} report={report} />)}
    {report.more_matches && <p>More passages match. Narrow the topic to inspect a different selection.</p>}
    <h4>Recorded conflicting accounts</h4><p className="subtle">These are your saved decisions with their supporting passages. Intentional ambiguity and author resolutions remain visible; no account is chosen automatically.</p>
    {report.conflicts.map(entry => <DecisionEvidence key={entry.id} entry={entry} label={conflictLabels[entry.stance]} />)}
    {!report.conflicts.length && <p>No recorded conflict matched this topic. Unrecorded contradictions may still exist.</p>}
    {report.more_conflicts && <p>Showing six matching decisions. Narrow the topic for others.</p>}
    {!!report.decisions.length && <details><summary>Inspect linked knowledge decisions ({report.decisions.length})</summary><div className="form-stack authoring-history">{report.decisions.map(entry => <DecisionEvidence key={entry.id} entry={entry} label={knowledgeLabels[entry.stance]} />)}</div></details>}
    <p className="subtle">An excerpt marked differently for two characters can help you plan a reveal. This view does not grant knowledge, compose a character’s briefing, or advance the scene. Refresh after changes made elsewhere.</p>
    <button className="button" onClick={onDecisions}>Review author decisions</button>
    <details><summary>Rehearsal boundary</summary><pre className="authoring-prose" tabIndex={0}>{JSON.stringify(report.boundary, null, 2)}</pre></details>
  </section>
}

function EvidenceCard({ item, report }: { item: RehearsalItem; report: RehearsalReport }) {
  return <article className="prepared-card form-stack"><SourceExcerpt source={item.source} />
    <small>Matched wording: {item.matched.join(', ')}</small>
    {item.different_states && <strong>Different recorded knowledge states</strong>}
    {!!item.knowledge.length && <ul className="rehearsal-knowledge">{item.knowledge.map(cell => {
      const view = report.views.find(view => view.key === cell.view)!
      const retained = cell.states.includes('unaware') && cell.decision_ids.some(id => !report.decisions.some(entry => entry.id === id))
      return <li key={cell.view}><strong>{viewpointLabel(view)}</strong>: {cell.states.map(state => knowledgeLabels[state]).join(' · ')}{retained && <small> · an earlier restriction is retained until author review</small>}</li>
    })}</ul>}
  </article>
}

function SourceExcerpt({ source }: { source: Source }) {
  return <><strong>{source.name ?? source.title}{source.edition ? ' · edition ' + source.edition : ''}{source.field ? ' · ' + source.field : ''}</strong><small>Characters {source.start + 1}–{source.end}</small><pre className="authoring-prose" tabIndex={0}>{source.text}</pre><details><summary>Source identity</summary><pre className="authoring-prose" tabIndex={0}>{source.id}{'\nSHA-256: '}{source.sha256}</pre></details></>
}

function DecisionEvidence({ entry, label }: { entry: RehearsalDecision; label: string }) {
  return <article className="prepared-card form-stack"><h4>{entry.subject} · {label}</h4><p>{entry.text}</p><details><summary>Exact supporting evidence ({entry.sources.length})</summary><div className="form-stack authoring-history">{entry.sources.map(source => <div className="form-stack" key={source.id}><SourceExcerpt source={source} /></div>)}</div></details></article>
}

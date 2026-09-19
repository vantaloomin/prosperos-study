import { useState } from 'react'
import { ErrorNotice } from '../../components/Feedback'
import { hiddenReason, suggestion } from './preferences'
import type { PhraseEvidence, PhraseFinding, PhrasePreferences, PhraseReport } from './types'

interface Props {
  report: PhraseReport; preferences: PhrasePreferences; stale: boolean
  onChoice: (finding: PhraseFinding, kind: 'dismissed' | 'intentional') => void
  onRead: (nodeId: string) => void
}

export function PhraseFindings({ report, preferences, stale, onChoice, onRead }: Props) {
  const visible = report.findings.filter(finding => !hiddenReason(preferences, finding))
  return <section className="form-stack" aria-label="Phrase observations">
    <p role="status">{report.passage_count} accepted prose passages checked · {report.word_count.toLocaleString()} words · {visible.length} observations shown.</p>
    {report.limited && <p className="notice">This check reached its size limit ({report.character_limit.toLocaleString()} characters or {report.word_limit.toLocaleString()} words). It covers {report.passage_count ? 'the most recent complete passages that fit' : 'no complete passages; the latest passage is too large for this check'}. Earlier text has not been checked.</p>}
    {!report.passage_count && !report.limited && <p>Add accepted prose to this path before checking wording.</p>}
    {!!report.passage_count && !visible.length && <p>No unhidden phrase matches meet these settings. This check does not evaluate meaning or pacing.</p>}
    {visible.map(finding => <PhraseCard key={finding.id} finding={finding} stale={stale} onChoice={kind => onChoice(finding, kind)} onRead={onRead} />)}
    {report.more_findings && <p className="subtle">Showing up to 30 groups of repeated wording. Choose a smaller scope or a higher occurrence minimum to narrow the check.</p>}
    <p className="subtle">Matches contain 3–8 words. Capitalization, apostrophe style, and spacing are normalized; sentence boundaries are retained. Overlapping fragments are grouped, and phrases made entirely of common words are omitted. Passage numbers refer to this check.</p>
  </section>
}

function PhraseCard({ finding, stale, onChoice, onRead }: {
  finding: PhraseFinding; stale: boolean; onChoice: (kind: 'dismissed' | 'intentional') => void; onRead: (id: string) => void
}) {
  return <article className="prepared-card phrase-finding form-stack">
    <h3>“{finding.phrase}”</h3><p>{finding.count} occurrences in {finding.passage_count} passage{finding.passage_count === 1 ? '' : 's'}.</p>
    <details><summary>Compare exact excerpts</summary><div className="form-stack phrase-evidence">{finding.evidence.map(source => <Evidence key={`${source.node_id}:${source.start}`} source={source} stale={stale} onRead={onRead} />)}
      {!!finding.omitted_evidence && <p className="subtle">{finding.omitted_evidence} additional occurrences counted. The first two and latest six are shown.</p>}</div></details>
    <PhraseSuggestion phrase={finding.phrase} stale={stale} />
    <div className="import-downloads"><button className="button" disabled={stale} onClick={() => onChoice('dismissed')}>Dismiss this observation</button><button className="button" disabled={stale} onClick={() => onChoice('intentional')}>Keep as intentional</button></div>
  </article>
}

function Evidence({ source, stale, onRead }: { source: PhraseEvidence; stale: boolean; onRead: (id: string) => void }) {
  return <div><small>Passage {source.passage} · characters {source.start + 1}–{source.end}</small>
    <blockquote>{source.more_before && '…'}{source.before}<mark>{source.quote}</mark>{source.after}{source.more_after && '…'}</blockquote>
    <button className="text-button" disabled={stale} onClick={() => onRead(source.node_id)}>Read passage {source.passage} in story</button>
  </div>
}

function PhraseSuggestion({ phrase, stale }: { phrase: string; stale: boolean }) {
  const [text, setText] = useState(suggestion(phrase, 'vary'))
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const choose = (kind: 'vary' | 'trim') => { setText(suggestion(phrase, kind)); setMessage(''); setError('') }
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setMessage('Copied. Paste it into an author’s note or your own revision instructions when you choose.'); setError('') }
    catch { setError('Clipboard access was unavailable. Select and copy the guidance text below.'); setMessage('') }
  }
  return <details><summary>Suggestions to consider</summary><div className="form-stack phrase-suggestions">
    <p>Consider varying the wording or trimming an occurrence. Deliberate rhythm, refrains, and character habits may be worth keeping.</p>
    <div className="import-downloads"><button className="button" disabled={stale} onClick={() => choose('vary')}>Suggest variation</button><button className="button" disabled={stale} onClick={() => choose('trim')}>Suggest trimming</button></div>
    <label className="field"><span>Editable guidance</span><textarea rows={4} value={text} disabled={stale} onChange={event => { setText(event.target.value); setMessage('') }} /></label>
    <button className="button" disabled={stale || !text.trim()} onClick={() => void copy()}>Copy guidance</button>
    <p className="subtle">Copying leaves your manuscript and future writing requests unchanged until you use the guidance.</p>
    {message && <p role="status">{message}</p>}<ErrorNotice message={error} />
  </div></details>
}

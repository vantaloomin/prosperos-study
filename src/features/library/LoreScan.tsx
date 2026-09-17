import { useRef, useState } from 'react'
import { api } from '../../api'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { LoreDefinition, LoreScan as Scan } from './loreTypes'

export function LoreScan({ definition, onClose }: { definition: LoreDefinition; onClose: () => void }) {
  const [passage, setPassage] = useState('')
  const [prior, setPrior] = useState('')
  const [clock, setClock] = useState(0)
  const [rng, setRng] = useState(false)
  const [seed, setSeed] = useState('lore-preview')
  const [result, setResult] = useState<Scan | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const action = useAction()
  const run = () => action.run(async () => {
    const prior_passages = prior ? prior.split('\n---\n') : []
    setResult(await api<Scan>('/lore/preview', { definition, passage, prior_passages, completed_beats: clock, master_rng: rng, seed }))
    requestAnimationFrame(() => heading.current?.focus())
  })
  return <Modal open wide title="Test Canon rules" description="A private simulation of your unpublished draft. No Story, live rolls or accepted history changes." onClose={onClose}>
    <div className="dialog-body form-stack"><TextField label="Passage to test" value={passage} rows={5} maxLength={100000} autoFocus onChange={(e) => setPassage(e.target.value)} />
      <details className="advanced-settings"><summary>Simulate beats and chance</summary><div className="form-stack character-advanced">
        <Field label="Completed beats before this passage" type="number" value={clock} min={0} max={1000000} onChange={(e) => setClock(Number(e.target.value))} />
        <TextField label="Earlier test passages" value={prior} rows={4} onChange={(e) => setPrior(e.target.value)} hint="Separate completed beats with a line containing ---. Include these beats in the count above. At most 50 passages." />
        <label className="check-row"><input type="checkbox" checked={rng} onChange={(e) => setRng(e.target.checked)} />Enable RNG in this simulation</label>
        <Field label="Simulation seed" value={seed} maxLength={200} onChange={(e) => setSeed(e.target.value)} hint="The same draft, passages and seed reproduce the same result. This seed is never used by a live Story." />
      </div></details><ErrorNotice message={action.error} />
      {result && <section className="lore-scan-results"><h3 ref={heading} tabIndex={-1}>Scan results · simulated beat {result.after.clock}</h3><p className="subtle">{result.notice} Results describe the inputs at the last scan.</p><ScanResults result={result} /></section>}
    </div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Done</button><button className="button primary" aria-disabled={action.busy} onClick={run}>{action.busy ? 'Scanning…' : 'Run test scan'}</button></footer>
  </Modal>
}

function ScanResults({ result }: { result: Scan }) {
  const budget = result.budgets[0]
  return <><p className="subtle">Scanned {budget.scanned_messages} contributions · required {budget.required_tokens} estimated tokens · flavor {budget.flavor_used_tokens} / {budget.flavor_budget_tokens} · {result.draws.length} simulated draws</p>
    {result.entries.length === 0 && <p>No entries to scan. Add an entry to the draft first.</p>}
    {result.entries.map((entry) => <article key={entry.entry_id} className="lore-result"><strong>{entry.title}</strong><span className="eyebrow">{entry.included ? 'Included' : 'Excluded'}</span><p>{entry.reason}</p><small>Matched: {[...entry.matched.primary, ...entry.matched.secondary].join(', ') || 'none'}{entry.roll !== null && ` · d100: ${entry.roll}`}</small></article>)}
    {result.sources.length > 0 && <details className="advanced-settings"><summary>Selected reference text</summary>{result.sources.map((source) => <section key={source.id}><h4>{source.title} · {source.placement}</h4><pre className="lore-prose-preview">{source.text.slice(0, 20000)}</pre>{source.text.length > 20000 && <p className="subtle">Showing the first 20,000 characters.</p>}</section>)}</details>}
    {result.timeline.length > 0 && <details className="advanced-settings"><summary>Earlier simulated beats</summary>{result.timeline.map((scan, index) => <p key={index}>Beat {scan.after.clock}: {scan.entries.filter((item) => item.included).map((item) => item.title).join(', ') || 'no included entries'} · {scan.draws.length} draws</p>)}</details>}
  </>
}

import { Field, TextField } from '../../components/Fields'
import type { LoreDefinition, LoreEntry } from './loreTypes'

type Props = { entry: LoreEntry; onChange: (patch: Partial<LoreEntry>) => void }

export function LoreRules({ entry, onChange }: Props) {
  return <details className="advanced-settings"><summary>When and how to include this entry</summary><div className="form-stack character-advanced">
    <label className="field"><span>Activation</span><select value={entry.activation} onChange={(e) => onChange({ activation: e.target.value as LoreEntry['activation'] })}><option value="always">Always eligible</option><option value="keywords">Match keywords</option></select></label>
    {entry.activation === 'keywords' && <><TextField label="Primary keywords" hint="One literal word or phrase per line. No regular expressions or macros." value={entry.keywords.join('\n')} onChange={(e) => onChange({ keywords: terms(e.target.value) })} rows={3} /><label className="field"><span>Primary match</span><select value={entry.match} onChange={(e) => onChange({ match: e.target.value as LoreEntry['match'] })}><option value="any">Any keyword</option><option value="all">All keywords</option></select></label></>}
    <SecondaryRules entry={entry} onChange={onChange} />
    <label className="check-row"><input type="checkbox" checked={entry.case_sensitive} onChange={(e) => onChange({ case_sensitive: e.target.checked })} />Match letter case</label>
    <label className="check-row"><input type="checkbox" checked={entry.whole_words} onChange={(e) => onChange({ whole_words: e.target.checked })} />Match whole words and phrases</label>
    <PlacementRules entry={entry} onChange={onChange} />
    <BeatRules entry={entry} onChange={onChange} />
  </div></details>
}

function terms(text: string) { return text ? text.split('\n') : [] }

function SecondaryRules({ entry, onChange }: Props) {
  return <><label className="field"><span>Secondary condition</span><select value={entry.secondary_mode} onChange={(e) => onChange({ secondary_mode: e.target.value as LoreEntry['secondary_mode'] })}><option value="none">No extra condition</option><option value="require">Also require any secondary keyword</option><option value="exclude">Exclude when any secondary keyword appears</option></select></label>
    {entry.secondary_mode !== 'none' && <TextField label="Secondary keywords" hint="One literal word or phrase per line." value={entry.secondary.join('\n')} onChange={(e) => onChange({ secondary: terms(e.target.value) })} rows={3} />}</>
}

function PlacementRules({ entry, onChange }: Props) {
  return <><label className="field"><span>Importance</span><select value={entry.kind} onChange={(e) => onChange({ kind: e.target.value as LoreEntry['kind'], chance_enabled: false, cooldown_beats: 0 })}><option value="required">Required reference · never randomly omitted</option><option value="flavor">Optional flavor · subject to budget</option></select></label>
    <label className="field"><span>Placement</span><select value={entry.placement} onChange={(e) => onChange({ placement: e.target.value as LoreEntry['placement'] })}><option value="header">Before story history</option><option value="recent">With recent context</option><option value="tail">After story history</option></select></label>
    <Field label="Priority" type="number" min={-1000} max={1000} value={entry.priority} onChange={(e) => onChange({ priority: Number(e.target.value) })} hint="Higher priority first. Required references do not consume the optional flavor budget." /></>
}

function BeatRules({ entry, onChange }: Props) {
  return <><div className="form-grid"><Field label="Minimum completed beats" type="number" min={0} max={10000} value={entry.minimum_beats} onChange={(e) => onChange({ minimum_beats: Number(e.target.value) })} /><Field label="Extra beats to retain" type="number" min={0} max={1000} value={entry.sticky_beats} onChange={(e) => onChange({ sticky_beats: Number(e.target.value) })} /></div>
    <p className="subtle">Retained entries still respect their toggle and secondary exclusions. Beat timing can be explored in the isolated test scan.</p>
    {entry.kind === 'flavor' && <><Field label="Cooldown after retention" type="number" min={0} max={1000} value={entry.cooldown_beats} onChange={(e) => onChange({ cooldown_beats: Number(e.target.value) })} />
      <label className="check-row"><input type="checkbox" checked={entry.chance_enabled} onChange={(e) => onChange({ chance_enabled: e.target.checked })} />Use a chance gate</label>
      {entry.chance_enabled && <Field label="Chance percent" type="number" min={0} max={100} value={entry.chance} onChange={(e) => onChange({ chance: Number(e.target.value) })} />}
      <p className="subtle">With chance or master RNG off, eligible flavor is deterministic. Switch the entry off to exclude it entirely.</p></>}
  </>
}

export function LoreBookRules({ value, onChange }: { value: LoreDefinition; onChange: (value: LoreDefinition) => void }) {
  return <details className="advanced-settings"><summary>Book scan and budget</summary><div className="form-stack character-advanced">
    <Field label="Recent contributions to scan" type="number" min={1} max={1000} value={value.scan_messages} onChange={(e) => onChange({ ...value, scan_messages: Number(e.target.value) })} hint="Out-of-character notes are excluded. Matching does not scan other entries recursively." />
    <Field label="Optional flavor budget · estimated tokens" type="number" min={0} max={1000000} value={value.flavor_budget_tokens} onChange={(e) => onChange({ ...value, flavor_budget_tokens: Number(e.target.value) })} hint="Required references remain eligible even when this budget is zero. Estimates use UTF-8 size, not a model tokenizer." />
  </div></details>
}

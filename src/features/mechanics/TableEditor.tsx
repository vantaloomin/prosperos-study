import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { TableDefinition, TableRow, TableVersion } from './types'

const empty: TableDefinition = { id: '', name: '', die: 10, purpose: 'extra', note: '', low_overflow: null, high_overflow: null, rows: [{ id: 'result-1', low: 1, high: 10, label: 'An opening', instruction: 'An appropriate opening presents itself within the current situation.', kind: 'event', child: null, major: false, tags: [] }] }

export function TableEditor({ tableId, onClose }: { tableId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['table-versions', tableId], queryFn: () => api<TableVersion[]>(`/roll-tables/${tableId}/versions`), enabled: !!tableId })
  const ready = !tableId || !!query.data
  return <Modal open onClose={onClose} title={tableId ? 'Shape the possibilities' : 'A new table'} description="Edit the meaning, preserve the history. Every die face must be covered exactly once." wide><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{!ready && !query.error && <Loading />}{ready && <TableForm tableId={tableId} versions={query.data ?? []} onClose={onClose} />}</div></Modal>
}

function TableForm({ tableId, versions, onClose }: { tableId: string; versions: TableVersion[]; onClose: () => void }) {
  const latest = versions[0]
  const [draft, setDraft] = usePersistent(`roleplay:table-draft:${tableId || 'new'}:${latest?.id ?? ''}`, latest?.definition ?? empty)
  const action = useAction()
  const patch = (change: Partial<TableDefinition>) => setDraft({ ...draft, ...change })
  const updateRow = (index: number, row: TableRow) => patch({ rows: draft.rows.map((current, i) => i === index ? row : current) })
  const addRow = () => patch({ rows: [...draft.rows, { ...empty.rows[0], id: `result-${crypto.randomUUID()}`, low: draft.die + 1, high: draft.die + 1 }], die: draft.die + 1 })
  const publish = () => action.run(async () => {
    await api(`/roll-tables/${draft.id}`, { operation_id: operationId(), expected_version_id: latest?.id ?? null, definition: draft }, 'PUT')
    if (!tableId) setDraft(empty)
    onClose()
  })
  return <><p className="subtle">{latest ? `Editing library v${latest.number}. Your draft stays on this device when you close the editor.` : 'Choose a stable identifier such as quiet-discoveries. New tables can be used as optional inspiration or story textures.'}</p><div className="mechanic-fields"><Field label="Table name" value={draft.name} onChange={(e) => patch({ name: e.target.value })} /><Field label="Stable table identifier" value={draft.id} disabled={!!tableId} onChange={(e) => patch({ id: e.target.value })} /><Field label="Die faces" type="number" min={1} max={1000} value={draft.die} onChange={(e) => patch({ die: Number(e.target.value) })} /></div><TextField label="Table notes" rows={2} value={draft.note} onChange={(e) => patch({ note: e.target.value })} /><div className="table-editor-rows">{draft.rows.map((row, index) => <RowEditor key={row.id} row={row} onChange={(value) => updateRow(index, value)} onRemove={() => patch({ rows: draft.rows.filter((_, i) => i !== index) })} />)}</div><button className="button" onClick={addRow}>Add result & die face</button><AdvancedDefinition draft={draft} onChange={setDraft} /><VersionChoices versions={versions} onRestore={setDraft} /><ErrorNotice message={action.error} /><div className="mechanics-footer"><p className="subtle">Stories adopt new table versions through Randomness controls. Existing rolls remain reproducible.</p><button className="button primary" disabled={action.busy || !draft.id || !draft.name} onClick={publish}>Publish new version</button></div></>
}

function RowEditor({ row, onChange, onRemove }: { row: TableRow; onChange: (row: TableRow) => void; onRemove: () => void }) {
  const patch = (change: Partial<TableRow>) => onChange({ ...row, ...change })
  return <details className="table-row-editor"><summary><span>{row.low}–{row.high}</span>{row.label}</summary><div className="form-stack"><div className="mechanic-fields"><Field label="From face" type="number" min={1} value={row.low} onChange={(e) => patch({ low: Number(e.target.value) })} /><Field label="Through face" type="number" min={1} value={row.high} onChange={(e) => patch({ high: Number(e.target.value) })} /><Field label="Result label" value={row.label} onChange={(e) => patch({ label: e.target.value })} /></div><TextField label="Narrative instruction" rows={3} value={row.instruction} onChange={(e) => patch({ instruction: e.target.value })} /><label className="field"><span>Outcome type</span><select value={row.kind} onChange={(e) => patch({ kind: e.target.value as TableRow['kind'] })}><option value="event">Narrative instruction</option><option value="no_event">Intentional no event</option><option value="progress">Uninterrupted progress</option></select></label><Field label="Child table identifier (optional)" value={row.child ?? ''} onChange={(e) => patch({ child: e.target.value || null })} /><label className="check-row"><input type="checkbox" checked={row.major} onChange={(e) => patch({ major: e.target.checked })} />Counts as a major disruption</label><button className="text-button" onClick={onRemove}>Remove from this unpublished draft</button></div></details>
}

function VersionChoices({ versions, onRestore }: { versions: TableVersion[]; onRestore: (definition: TableDefinition) => void }) {
  return <details className="mechanics-advanced"><summary>Preserved library versions ({versions.length})</summary><div className="form-stack">{versions.map((version) => <div className="mechanics-footer" key={version.id}><span className="subtle">v{version.number} · {new Date(version.created_at).toLocaleString()}</span><button className="text-button" onClick={() => onRestore(version.definition)}>Use v{version.number} as this draft</button></div>)}</div></details>
}

function AdvancedDefinition({ draft, onChange }: { draft: TableDefinition; onChange: (definition: TableDefinition) => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const load = async () => {
    try { const checked = await api<TableDefinition>('/roll-tables/validate', JSON.parse(text)); onChange(checked); setError('') }
    catch (error) { setError(error instanceof Error ? error.message : 'The table could not be read.') }
  }
  return <details className="mechanics-advanced"><summary>Advanced definition / import JSON</summary><div className="form-stack"><p className="subtle">Includes stable IDs, carrier tags, exceptional handling outcomes and table purpose. Loading validates a draft; publishing is a separate action.</p><button className="text-button" onClick={() => setText(JSON.stringify(draft, null, 2))}>Copy current definition into editor</button><TextField label="Table JSON" rows={12} value={text} onChange={(e) => setText(e.target.value)} /><ErrorNotice message={error} /><button className="button" onClick={() => void load()} disabled={!text.trim()}>Validate & load draft</button></div></details>
}

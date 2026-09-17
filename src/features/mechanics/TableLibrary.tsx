import { useState } from 'react'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { MechanicsContext, Outcome, TableVersion } from './types'
import { TableEditor } from './TableEditor'

export function TableLibrary({ data }: { data: MechanicsContext }) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('narrative-push')
  const [editing, setEditing] = useState<string | null>(null)
  const filtered = data.tables.filter((table) => table.definition.name.toLowerCase().includes(search.toLowerCase()))
  const table = data.tables.find((item) => item.table_id === selected)
  return <div className="form-stack"><div className="mechanics-footer"><p className="subtle">This story's selected table versions. Publishing creates a new library version; existing pinned stories and roll records stay unchanged.</p><button className="button" onClick={() => setEditing('')}>New table</button></div><Field label="Find a table" value={search} onChange={(e) => setSearch(e.target.value)} /><label className="field"><span>Table</span><select value={selected} onChange={(e) => setSelected(e.target.value)}><option value="" disabled>Choose a table</option>{filtered.map((item) => <option key={item.table_id} value={item.table_id}>{item.definition.name} · v{item.number}</option>)}</select></label>{table && <TableDetail key={table.id} table={table} data={data} onEdit={() => setEditing(table.table_id)} />}{editing !== null && <TableEditor tableId={editing} onClose={() => setEditing(null)} />}</div>
}

function TableDetail({ table, data, onEdit }: { table: TableVersion; data: MechanicsContext; onEdit: () => void }) {
  const [preview, setPreview] = useState<{ result: Outcome; seed: string; draws: unknown[] } | null>(null)
  const action = useAction()
  const test = () => action.run(async () => { setPreview(await api(`/roll-tables/${table.table_id}/preview`, { settings: data.settings, seed: crypto.randomUUID() })) })
  return <><div><h3>{table.definition.name} <small>v{table.number} · d{table.definition.die}</small></h3><p className="subtle">{table.definition.note}</p></div><div className="table-reading-list">{table.definition.rows.map((row) => <div key={row.id}><span>{row.low === row.high ? row.low : `${row.low}–${row.high}`}</span><p><strong>{row.label}</strong><br />{row.instruction}{row.child && <small>Followed by {row.child}</small>}</p></div>)}</div><div className="preset-buttons"><button className="button" onClick={onEdit}>Edit library table & versions</button><button className="button" onClick={test} disabled={action.busy}>Test roll · no story changes</button></div><ErrorNotice message={action.error} />{preview && <div className="prepared-card"><h3>Preview only · {preview.result.status?.replaceAll('_', ' ')}</h3><p className="subtle">{preview.result.reason || preview.result.chain?.map((item) => item.row.label).join(' → ')}</p><details className="input-inspector"><summary>Preview seed & draws</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details></div>}</>
}

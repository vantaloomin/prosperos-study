import { useMemo, useState } from 'react'
import { Modal } from '../../components/Modal'
import { Field } from '../../components/Fields'
import type { Message } from '../../types'
import { findPassages } from './transcriptWindow'

export function PassageFinder({ messages, onSelect, onClose }: { messages: Message[]; onSelect: (index: number) => void; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const matches = useMemo(() => findPassages(messages, query), [messages, query])
  return <Modal open onClose={onClose} title="Find a passage" description="Search the entire selected path, or enter a contribution number. Every original message remains available.">
    <div className="dialog-body form-stack"><Field label="Text or contribution number" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0) }} autoFocus />
      <p className="subtle" role="status">{matches.length.toLocaleString()} matching contributions</p><div className="passage-results">{matches.slice(page * 30, (page + 1) * 30).map((index) => <button className="passage-result" key={messages[index].id} onClick={() => onSelect(index)}><strong>Contribution {index + 1}</strong><span>{messages[index].text.slice(0, 180)}</span></button>)}</div></div>
    <footer className="dialog-footer"><button className="button quiet" disabled={!page} onClick={() => setPage(page - 1)}>Previous results</button><span className="subtle">{page + 1} / {Math.max(1, Math.ceil(matches.length / 30))}</span><button className="button quiet" disabled={(page + 1) * 30 >= matches.length} onClick={() => setPage(page + 1)}>Next results</button></footer>
  </Modal>
}

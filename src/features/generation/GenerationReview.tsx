import { useState } from 'react'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Generation } from './types'
import { useGeneration } from './useGeneration'
import { RollInspector } from '../mechanics/RollInspector'
import { LoreReceiptView } from '../library/LoreReceiptView'
import { TellingBrowser } from './TellingBrowser'

export function GenerationReview({ id, initialCandidateId = '', onClose, onBranch }: { id: string; initialCandidateId?: string; onClose: () => void; onBranch: (id: string) => void }) {
  const [origin] = useState(() => document.activeElement as HTMLElement | null)
  const query = useGeneration(id)
  return <Modal open onClose={onClose} focusOnClose={() => origin?.isConnected ? origin : document.querySelector<HTMLElement>('[aria-label="Story message"]')} title="A possible next moment" description="Drafts are separate from the story. Keep the version that feels right, or leave every path open." wide>
    {query.error && <ErrorNotice message={query.error.message} />}
    {query.data ? <TellingBrowser generation={query.data} initialId={initialCandidateId} onBranch={onBranch} onClose={onClose} inspector={<InputInspector generation={query.data} />} /> : <div className="dialog-body"><Loading label="Opening drafts…" /></div>}
  </Modal>
}

function InputInspector({ generation }: { generation: Generation }) {
  const { snapshot } = generation
  const [roll, setRoll] = useState(false)
  return <>{snapshot.lore && <LoreReceiptView receipt={snapshot.lore} />}<details className="input-inspector"><summary>Reveal full inputs, including Canon and private background</summary><p className="subtle">Complete selected path: {snapshot.coverage.messages} messages. Estimated input: {snapshot.estimated_input_tokens.toLocaleString()} tokens (approximation). Prompt v{snapshot.prompt.number}.</p><h4>Role instructions</h4><pre>{snapshot.prompt.template}</pre><h4>Story context</h4><pre>{JSON.stringify(JSON.parse(snapshot.content), null, 2)}</pre></details>{snapshot.opportunity_id && <button className="text-button" onClick={() => setRoll(true)}>Inspect the preserved mechanical proposal</button>}{roll && snapshot.opportunity_id && <RollInspector id={snapshot.opportunity_id} onClose={() => setRoll(false)} />}</>
}

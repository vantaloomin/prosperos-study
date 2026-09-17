import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { OutcomeSummary } from '../mechanics/OutcomeSummary'
import type { BackgroundRecord } from './types'
import { PrivateContentView } from './PrivateContentView'

export function BackgroundReveal({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['background-reveal', id], queryFn: () => api<BackgroundRecord>(`/background/${id}/reveal`) })
  return <Modal open onClose={onClose} title="Behind this path" description="Revealed private inspiration. These cues are not established facts or inevitable events." wide><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}{query.data && <RevealedBackground record={query.data} />}</div></Modal>
}

function RevealedBackground({ record }: { record: BackgroundRecord }) {
  const { snapshot } = record
  const targets = {
    drives: snapshot.result.drives.map((item, index) => ({ id: `drive:${index}`, character: item.character })),
    hooks: snapshot.result.hooks.map((item, index) => ({ id: `hook:${index}`, day: item.day })),
  }
  return <><p className="subtle">Day {snapshot.day} from “{snapshot.recipe.origin}”. Character drives {snapshot.drives_enabled ? 'enabled' : 'paused'}; future hooks {snapshot.hooks_enabled ? 'enabled' : 'paused'}.</p>
    {snapshot.interpretation && <section className="form-stack"><h3>Selected private interpretation</h3><p className="subtle">These are preserved possibilities, not established events. Paused features retain their details but do not guide new responses.</p><PrivateContentView content={snapshot.interpretation.content} targets={targets} /></section>}
    {snapshot.result.drives.map((drive, index) => <section className="prepared-card" key={index}><h3>{drive.character.name}</h3>{drive.results.map((outcome, resultIndex) => <OutcomeSummary key={resultIndex} title={resultIndex === 0 ? 'Drive cue' : 'Complicating cue'} outcome={outcome} />)}</section>)}
    {snapshot.result.hooks.map((hook, index) => <section key={index} className="prepared-card"><h3>Hook {index + 1}{hook.day === null ? ' · no date drawn' : ` · day ${hook.day}`}</h3><OutcomeSummary title="Possibility" outcome={hook.result} /></section>)}
    <details className="input-inspector"><summary>Preserved seed, draws, versions & settings</summary><pre>{JSON.stringify(snapshot, null, 2)}</pre></details>
  </>
}

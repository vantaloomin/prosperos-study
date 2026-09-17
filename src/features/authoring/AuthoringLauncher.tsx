import { lazy, Suspense, useState } from 'react'
import { Loading } from '../../components/Feedback'
import type { EditorProps } from './types'

const AuthoringDialog = lazy(() => import('./AuthoringDialog').then((module) => ({ default: module.AuthoringDialog })))

export function AuthoringLauncher(props: EditorProps) {
  const [open, setOpen] = useState(false)
  const start = () => {
    if (!props.asset && !props.draft.assistance_id) props.onChange({ ...props.draft, assistance_id: props.draftId })
    setOpen(true)
  }
  return <section className="authoring-launch"><h3>A second pair of eyes</h3><p className="subtle">Draft, critique or tighten a passage. Review every suggestion before adding it to your unpublished draft.</p>
    <button className="button" onClick={start}>Writing assistant</button>
    {open && <Suspense fallback={<Loading />}><AuthoringDialog {...props} onClose={() => setOpen(false)} /></Suspense>}
  </section>
}

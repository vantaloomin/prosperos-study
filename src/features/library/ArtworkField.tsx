import { useEffect, useRef, useState } from 'react'
import { ImagePlus } from 'lucide-react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { readImportFile, type ImportPreview } from './importTypes'
import { artworkUrl } from './artworkUrl'

interface Props { value?: string | null; onChange: (value: string | null) => void; onCard?: (preview: ImportPreview) => void; onBusy?: (busy: boolean) => void }
interface Uploaded { sha256: string; import_preview?: ImportPreview }

export function ArtworkField({ value, onChange, onCard, onBusy }: Props) {
  const action = useAction()
  const [removed, setRemoved] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const current = useRef({ onChange, onCard, onBusy, mounted: true })
  const chooser = useRef<HTMLInputElement>(null)
  useEffect(() => { current.current = { ...current.current, onChange, onCard, onBusy } }, [onChange, onCard, onBusy])
  useEffect(() => { current.current.mounted = true; return () => { current.current.mounted = false; current.current.onBusy?.(false) } }, [])
  useEffect(() => { current.current.onBusy?.(action.busy) }, [action.busy])
  const upload = (file?: File) => action.run(async () => {
    if (!file) return
    const source_base64 = await readImportFile(file)
    const result = await api<Uploaded>('/library-artwork', { source_base64, filename: file.name, detect_card: Boolean(onCard) })
    if (!current.current.mounted) return
    if (result.import_preview) { current.current.onCard?.(result.import_preview); return }
    current.current.onChange(result.sha256)
    setRemoved(null)
  })
  return <section className={`artwork-field${dragging ? ' dragging' : ''}`} aria-label="Artwork"
    onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
    onDrop={(event) => { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files[0]) }}>
    <button className="artwork-preview" aria-label={value ? 'Replace artwork' : 'Add artwork'} aria-disabled={action.busy} onClick={() => { if (!action.busy) chooser.current?.click() }}>
      {value ? <img src={artworkUrl(value)} alt="Current artwork" /> : <ImagePlus size={28} />}
    </button>
    <div className="artwork-controls"><strong>Artwork</strong><p className="subtle">Drop an image or choose a file. PNG, JPEG or WebP · 10 MiB · 16 million pixels.</p>
      {onCard && <p className="subtle">Dropping a PNG Character Card opens a review of its art and fields.</p>}
      <input ref={chooser} className="artwork-input" type="file" accept="image/png,image/jpeg,image/webp" aria-label="Choose artwork" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; void upload(file) }} />
      <div className="artwork-actions"><button className="button" disabled={action.busy} onClick={() => chooser.current?.click()}>{action.busy ? 'Preparing image…' : 'Choose image'}</button>
        {value && <><button className="text-button" disabled={action.busy} onClick={() => { setRemoved(value); onChange(null) }}>Remove artwork</button><a className="text-button" href={artworkUrl(value, 'original')}>Original</a></>}
        {removed && !value && <button className="text-button" onClick={() => { onChange(removed); setRemoved(null) }}>Undo removal</button>}
      </div><ErrorNotice message={action.error} />
    </div>
  </section>
}

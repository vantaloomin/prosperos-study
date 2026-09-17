import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch, Story } from '../../types'
import { messageLabels, storyMode, type StoryMode } from '../stories/storyMode'
import '../../styles/export.css'

interface Transcript { content: string; filename: string; download_url: string; branch_revision: number; message_count: number; omitted_ooc_count: number }
interface Options { from_node_id: string; through_node_id: string; include_ooc: boolean; include_timestamps: boolean; include_models: boolean }

export function TranscriptExport({ story, initialBranchId, onClose }: { story: Story; initialBranchId: string; onClose: () => void }) {
  const [branchId, setBranchId] = useState(initialBranchId)
  const query = useQuery({ queryKey: ['branch', branchId], queryFn: () => api<Branch>(`/branches/${branchId}`) })
  return <Modal open onClose={onClose} title="Take the words with you" description="A readable Markdown transcript of one path, ready to keep or share." wide><div className="dialog-body form-stack">
    <label className="field"><span>Branch to export</span><select value={branchId} onChange={(event) => setBranchId(event.target.value)}>{story.branches.map((branch) => <option value={branch.id} key={branch.id}>{branch.name}</option>)}</select></label>
    <p className="subtle">Includes saved story text only. Canon, hidden state, rolls, reviews, unused drafts and sidebar conversations stay outside this transcript. This is not a restorable backup.</p>
    <ErrorNotice message={query.error?.message} />
    {query.data ? <ExportOptions key={`${branchId}:${query.data.revision}`} branch={query.data} mode={storyMode(story.settings)} /> : <Loading label="Opening this path…" />}
  </div></Modal>
}

function ExportOptions({ branch, mode }: { branch: Branch; mode: StoryMode }) {
  const [options, setOptions] = useState<Options>({ from_node_id: '', through_node_id: '', include_ooc: false, include_timestamps: false, include_models: false })
  const [preview, setPreview] = useState<Transcript | null>(null)
  const action = useAction()
  const patch = (change: Partial<Options>) => { setOptions({ ...options, ...change }); setPreview(null) }
  const prepare = () => action.run(async () => {
    setPreview(null)
    setPreview(await api<Transcript>(`/branches/${branch.id}/transcript`, { ...options, expected_revision: branch.revision, from_node_id: options.from_node_id || null, through_node_id: options.through_node_id || null }))
  })
  return <div className="form-stack"><div className="export-range">
    <PassageBoundary branch={branch} mode={mode} label="Start of export" value={options.from_node_id} empty="Beginning of this branch" onChange={(from_node_id) => patch({ from_node_id })} />
    <PassageBoundary branch={branch} mode={mode} label="End of export" value={options.through_node_id} empty="Current end of this branch" onChange={(through_node_id) => patch({ through_node_id })} />
  </div>
    <label className="check-row"><input type="checkbox" checked={options.include_ooc} onChange={(event) => patch({ include_ooc: event.target.checked })} />Include {mode === 'roleplay' ? 'out-of-character notes' : 'author notes'}</label>
    <label className="check-row"><input type="checkbox" checked={options.include_timestamps} onChange={(event) => patch({ include_timestamps: event.target.checked })} />Include timestamps</label>
    <label className="check-row"><input type="checkbox" checked={options.include_models} onChange={(event) => patch({ include_models: event.target.checked })} />Include model names for generated contributions</label>
    <ErrorNotice message={action.error} /><button className="button export-action" aria-disabled={action.busy} onClick={prepare}>Preview transcript</button>
    {preview && <ExportPreview transcript={preview} />}
  </div>
}

function PassageBoundary({ branch, mode, label, value, empty, onChange }: { branch: Branch; mode: StoryMode; label: string; value: string; empty: string; onChange: (value: string) => void }) {
  const labels = messageLabels(mode)
  return <label className="field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">{empty}</option>{branch.messages.map((message, index) => <option key={message.id} value={message.id}>{index + 1} · {labels[message.role]} · {message.text.slice(0, 65)}</option>)}</select></label>
}

function ExportPreview({ transcript }: { transcript: Transcript }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [feedback, setFeedback] = useState('')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(transcript.content)
      setFeedback('Complete Markdown transcript copied.')
    } catch { setFeedback('Your browser could not access the clipboard. Use Download Markdown instead.') }
  }
  useEffect(() => { heading.current?.focus() }, [transcript])
  return <section className="export-preview form-stack"><h3 ref={heading} tabIndex={-1}>Your transcript is ready</h3><p className="subtle">{transcript.message_count.toLocaleString()} {transcript.message_count === 1 ? 'contribution' : 'contributions'} · {transcript.omitted_ooc_count.toLocaleString()} {transcript.omitted_ooc_count === 1 ? 'note' : 'notes'} omitted · branch revision {transcript.branch_revision}. The download contains exactly this prepared selection.</p>
    <pre aria-label="Markdown transcript preview">{transcript.content.slice(0, 8000)}</pre>
    {transcript.content.length > 8000 && <p className="subtle">Showing the first 8,000 characters. The download includes the complete selection.</p>}
    <div className="export-actions"><a href={transcript.download_url} className="button primary" download={transcript.filename}><Download size={16} />Download Markdown</a><button className="button" onClick={() => void copy()}>Copy Markdown</button></div><p role="status" className="subtle">{feedback}</p>
  </section>
}

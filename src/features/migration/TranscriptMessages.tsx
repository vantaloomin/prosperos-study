import { useState } from 'react'
import { roleLabels, type ImportRole, type TranscriptChoice, type TranscriptMessage } from './transcriptTypes'

export function TranscriptMessages({ messages, choices, onChange }: { messages: TranscriptMessage[]; choices: TranscriptChoice[]; onChange: (choices: TranscriptChoice[]) => void }) {
  const [page, setPage] = useState(0)
  const [speaker, setSpeaker] = useState(messages.find(message => !message.protected)?.speaker ?? '')
  const speakers = [...new Set(messages.filter(message => !message.protected).map(message => message.speaker))]
  const change = (index: number, patch: Partial<TranscriptChoice>) => onChange(choices.map(choice => choice.index === index ? { ...choice, ...patch } : choice))
  return <section className="form-stack"><h3>Review speakers and messages</h3><p className="subtle">Story text is accepted prose. Author notes are kept out of ordinary prose export. Reference-only messages and unchosen replies remain in the preserved source.</p>
    {!!speakers.length && <div className="migration-mapping"><label className="field"><span>Source speaker</span><select aria-label="Source speaker" value={speaker} onChange={event => setSpeaker(event.target.value)}>{speakers.map(label => <option key={label}>{label}</option>)}</select></label><label className="field"><span>Map this speaker to</span><select aria-label="Map this speaker to" value="" onChange={event => onChange(choices.map(choice => messages[choice.index].speaker === speaker && !messages[choice.index].protected ? { ...choice, role: event.target.value as ImportRole } : choice))}><option value="" disabled>Choose a role for their messages</option>{Object.entries(roleLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>}
    <p className="subtle">Messages {page * 20 + 1}–{Math.min(messages.length, (page + 1) * 20)} of {messages.length}, in original order.</p>
    {messages.slice(page * 20, (page + 1) * 20).map(message => <MessageReview key={message.index} message={message} choice={choices[message.index]} onChange={patch => change(message.index, patch)} />)}
    <nav className="migration-actions" aria-label="Transcript review pages"><button className="button" disabled={!page} onClick={() => setPage(page - 1)}>Previous messages</button><button className="button" disabled={(page + 1) * 20 >= messages.length} onClick={() => setPage(page + 1)}>Next messages</button></nav>
  </section>
}

function MessageReview({ message, choice, onChange }: { message: TranscriptMessage; choice: TranscriptChoice; onChange: (patch: Partial<TranscriptChoice>) => void }) {
  const label = `Message ${message.index + 1}`
  return <article className="migration-message"><h4>{label} · {message.speaker}</h4><p className="subtle">Source role: {message.source_role}{message.timestamp ? ` · ${message.timestamp}` : ''}</p>
    {message.protected ? <p className="subtle">Protected source role · reference only</p> : <label className="field"><span>{label} destination</span><select aria-label={`${label} destination`} value={choice.role} onChange={event => onChange({ role: event.target.value as ImportRole })}>{Object.entries(roleLabels).map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>}
    {message.variants.length > 1 && <label className="field"><span>{label} telling</span><select aria-label={`${label} telling`} value={choice.variant} onChange={event => onChange({ variant: Number(event.target.value) })}>{message.variants.map((_, index) => <option key={index} value={index}>{index === 0 ? 'Current source message' : `Alternative ${index}`}</option>)}</select></label>}
    <pre tabIndex={0} className="migration-prose">{message.variants[choice.variant] || '(Empty message)'}</pre>
  </article>
}

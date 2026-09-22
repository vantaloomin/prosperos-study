import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Story } from '../../types'
import { PromptCard, PromptEditor, type Prompt } from './Prompts'
import { agentMode, templateSettings, type AgentSettings, type AgentTemplate } from './agentSettings'

export function ModeGuidance({ storyId, disabled = false, onEdit }: { storyId?: string; disabled?: boolean; onEdit?: (prompt: Prompt) => void }) {
  const query = useQuery({ queryKey: ['mode-guidance', storyId ?? 'workspace'], queryFn: () => api<Prompt[]>(`/mode-guidance${storyId ? `?story_id=${storyId}` : ''}`) })
  const [editing, setEditing] = useState<Prompt | null>(null)
  return <section className="prompt-group"><h3>Mode guidance</h3><p className="subtle">Mode identity goes before the role prompt; character agency goes last. Each request records the exact versions and character name it used.</p><ErrorNotice message={query.error?.message} />{query.data?.map(item => <div className="routing-row" key={item.key}><div><strong>{item.label}</strong><small>Version {item.number}</small></div><button className="button quiet" disabled={disabled} aria-label={`Edit ${item.label} guidance`} onClick={() => (onEdit ?? setEditing)(item)}>Edit guidance</button></div>)}{editing && <PromptEditor prompt={editing} storyId={storyId} onClose={() => setEditing(null)} />}</section>
}

export function TemplateChoice({ experience, value, onChange }: { experience: unknown; value?: AgentSettings; onChange?: (value: AgentSettings) => void }) {
  const templates = useQuery({ queryKey: ['agent-templates'], queryFn: () => api<AgentTemplate[]>('/agent-templates') })
  const prompts = useQuery({ queryKey: ['prompts'], queryFn: () => api<Prompt[]>('/prompts') })
  const template = templates.data?.find(item => item.mode === agentMode(experience))
  if (!template || !prompts.data) return <><ErrorNotice message={(templates.error ?? prompts.error)?.message} /><Loading label="Loading agent defaults…" /></>
  const disabled = value?.agent_template.mode === template.mode ? value.disabled_prompts : template.disabled
  const names = prompts.data.flatMap(item => [item, ...(item.tasks ?? [])])
  const defaults = template.disabled.map(key => names.find(item => item.key === key)?.label ?? key)
  const toggle = (key: string) => onChange?.(templateSettings(template, disabled.includes(key) ? disabled.filter(item => item !== key) : [...disabled, key]))
  return <div className="form-stack"><TemplateDescription mode={template.mode} />
    {defaults.length > 0 && <p className="subtle">Off by default: {defaults.join(', ')}.</p>}
    {onChange && <details className="advanced-settings"><summary>Customize agents</summary>{prompts.data.filter(item => item.key !== 'library-assist').map(item => <div className="task-setting" key={item.key}><label className="check-row"><input type="checkbox" checked={!disabled.includes(item.key)} disabled={item.enabled === false} onChange={() => toggle(item.key)} />{item.label}{item.enabled === false && <small>Off in Settings &gt; Prompts</small>}</label>{item.tasks?.filter(task => !task.historical && !task.key.startsWith('authoring-')).map(task => <label className="check-row" key={task.key}><input type="checkbox" checked={!disabled.includes(task.key)} disabled={item.enabled === false || disabled.includes(item.key) || task.enabled_source === 'workspace'} onChange={() => toggle(task.key)} />{task.label}</label>)}</div>)}</details>}
  </div>
}

function TemplateDescription({ mode }: { mode: AgentTemplate['mode'] }) {
  return <><h3>Agents for this mode · {mode === 'active' ? 'Active' : 'Passive'}</h3><p className="subtle">{mode === 'active' ? 'Writer, Collaborator, background planning and Scribe memory tasks start enabled. Scene drafting and readers are available when you choose them.' : 'The complete writing, scene and review workflow starts enabled.'} Workspace switches remain in effect. Canon search aids use the workspace Scribe settings.</p></>
}

export function TemplateOffer({ value, onChange }: { value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void }) {
  const templates = useQuery({ queryKey: ['agent-templates'], queryFn: () => api<AgentTemplate[]>('/agent-templates') })
  const prompts = useQuery({ queryKey: ['prompts'], queryFn: () => api<Prompt[]>('/prompts') })
  const mode = agentMode(value.experience), template = templates.data?.find(item => item.mode === mode)
  const old = (value.disabled_prompts ?? []) as string[]
  const changed = template ? [...new Set([...old, ...template.disabled])].filter(key => old.includes(key) !== template.disabled.includes(key)) : []
  const labels = prompts.data?.flatMap(item => [item, ...(item.tasks ?? [])]) ?? []
  return <details className="advanced-settings"><summary>Agent Template · {((value.agent_template as AgentSettings['agent_template'])?.mode ?? 'workspace defaults')}</summary><p className="subtle">Changing experience keeps your current switches. Apply the {mode === 'active' ? 'Active' : 'Passive'} template explicitly to use its defaults.</p><ul>{changed.map(key => <li key={key}>{template?.disabled.includes(key) ? 'Turn off' : 'Turn on'}: {labels.find(item => item.key === key)?.label ?? key}</li>)}</ul><button type="button" className="button" disabled={!template} onClick={() => template && onChange({ ...value, ...templateSettings(template) })}>Use {mode === 'active' ? 'Active' : 'Passive'} template</button></details>
}

export function StoryAgents({ storyId }: { storyId: string }) {
  const [editing, setEditing] = useState<Prompt | null>(null)
  const story = useQuery({ queryKey: ['story', storyId], queryFn: () => api<Story>(`/stories/${storyId}`) })
  const prompts = useQuery({ queryKey: ['prompts', storyId], queryFn: () => api<Prompt[]>(`/prompts?story_id=${storyId}`) })
  if (!story.data || !prompts.data) return <><ErrorNotice message={story.error?.message || prompts.error?.message} /><Loading /></>
  return <><StoryAgentEditor key={story.data.revision} story={story.data} prompts={prompts.data} onEdit={setEditing} />{editing && <PromptEditor prompt={editing} storyId={storyId} onClose={() => setEditing(null)} />}</>
}

function StoryAgentEditor({ story, prompts, onEdit }: { story: Story; prompts: Prompt[]; onEdit: (prompt: Prompt) => void }) {
  const [settings, setSettings] = useState(story.settings)
  const action = useAction()
  const dirty = JSON.stringify(settings) !== JSON.stringify(story.settings)
  const disabled = (settings.disabled_prompts ?? []) as string[]
  const toggle = (key: string) => setSettings({ ...settings, disabled_prompts: disabled.includes(key) ? disabled.filter(item => item !== key) : [...disabled, key] })
  const save = () => action.run(async () => { await api(`/stories/${story.id}/agents`, { expected_revision: story.revision, disabled, template: (settings.agent_template as AgentSettings['agent_template'])?.mode ?? null, prompt_sections: settings.prompt_sections !== false }, 'PUT') })
  return <div className="form-stack"><h3>Agents in this Story</h3>{dirty && <p className="subtle" role="status">Save your agent choices before editing prompts or mode guidance.</p>}<TemplateOffer value={settings} onChange={setSettings} />{prompts.map(prompt => <div key={prompt.key}><PromptCard prompt={{ ...prompt, enabled: prompt.enabled_source !== 'workspace' && !disabled.includes(prompt.key) }} onEdit={() => onEdit(prompt)} editDisabled={dirty} disabled={action.busy || prompt.enabled_source === 'workspace'} onToggle={() => toggle(prompt.key)} storyId={story.id} />{prompt.enabled_source === 'workspace' && <p className="subtle">Off in Settings &gt; Prompts</p>}{prompt.tasks?.filter(task => !task.historical).map(task => <label className="check-row task-setting" key={task.key}><input type="checkbox" checked={!disabled.includes(task.key)} disabled={action.busy || disabled.includes(prompt.key) || prompt.enabled_source === 'workspace' || task.enabled_source === 'workspace'} onChange={() => toggle(task.key)} />{task.label}{task.enabled_source === 'workspace' && ' · Off in Settings > Prompts'}</label>)}</div>)}
    <label className="check-row"><input type="checkbox" checked={settings.prompt_sections !== false} onChange={event => setSettings({ ...settings, prompt_sections: event.target.checked })} />Compose mode and agency guidance with role prompts</label><p className="subtle">Turning this off sends only role instructions. Saved requests retain their original instructions.</p><ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy} onClick={save}>Save Story agents</button><ModeGuidance storyId={story.id} disabled={dirty} onEdit={onEdit} />
  </div>
}

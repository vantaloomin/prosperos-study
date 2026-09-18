import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { TaskSetting } from '../workflow/types'
import type { Prompt } from './Prompts'

export function TaskSettings({ prompt, storyId }: { prompt: Prompt; storyId?: string }) {
  const [viewing, setViewing] = useState<TaskSetting | null>(null)
  const query = useQuery({ queryKey: storyId ? ['prompts', storyId] : ['prompts'], queryFn: () => api<Prompt[]>(`/prompts${storyId ? `?story_id=${storyId}` : ''}`) })
  const current = query.data?.find(item => item.key === prompt.key) ?? prompt
  if (!current.tasks?.length) return null
  return <details className="advanced-settings task-settings"><summary>Tasks & retained settings ({current.tasks.length})</summary><p className="subtle">Task switches, earlier instructions and model assignments stay in effect. Combined readers may make separate requests for retained settings.</p>{current.tasks.map(task => <TaskRow key={task.key} task={task} prompt={current} storyId={storyId} onView={() => setViewing(task)} />)}{viewing && <TaskHistory task={viewing} onClose={() => setViewing(null)} />}</details>
}

function TaskRow({ task, prompt, storyId, onView }: { task: TaskSetting; prompt: Prompt; storyId?: string; onView: () => void }) {
  const action = useAction()
  const toggle = () => action.run(async () => {
    await api(`/prompts/${task.key}/activation`, { enabled: !task.enabled, expected_revision: prompt.activation_revision ?? 0 }, 'PUT')
  })
  const adopt = () => action.run(async () => {
    await api(`/prompts/${task.key}/adopt-combined${storyId ? `?story_id=${storyId}` : ''}`, { expected_version_id: task.prompt_id })
  })
  if (task.historical) return <div className="task-setting"><strong>{task.label} · historical task</strong><p className="subtle">Earlier instructions and model assignments remain saved for history and retries. New scenes use {prompt.label}; assign its model in Models by step.</p><button className="text-button" onClick={onView}>Read previous instructions</button></div>
  return <div className="task-setting form-stack"><label className="check-row"><input type="checkbox" checked={task.enabled} disabled={action.busy || prompt.enabled === false || !!storyId} onChange={toggle} /><span>{task.label}<small>{task.custom_prompt ? `Retained ${task.pinned ? 'Story pin' : 'custom prompt'} · v${task.number}` : `Uses ${prompt.label} instructions`}{task.profile_id && ' · task model assigned'}</small></span></label><div className="scene-actions"><button className="text-button" onClick={onView}>Read previous instructions</button>{task.custom_prompt && <button className="button quiet" disabled={action.busy} onClick={adopt}>Use {prompt.label} instructions</button>}</div><ErrorNotice message={action.error} /></div>
}

export function TaskHistory({ task, onClose }: { task: Pick<TaskSetting, 'key' | 'label' | 'prompt_id'>; onClose: () => void }) {
  const query = useQuery({ queryKey: ['prompt-history', task.key], queryFn: () => api<Prompt[]>(`/prompts/${task.key}/versions`) })
  return <Modal open title={`${task.label} · previous instructions`} description="Saved versions remain available for original requests and retries." onClose={onClose} wide><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{query.data?.map(version => <details className="input-inspector" key={version.id}><summary>Version {version.number}{version.id === task.prompt_id ? ' · retained task version' : ''}</summary><pre>{version.template}</pre></details>)}</div></Modal>
}

export function RetiredPrompts() {
  const [viewing, setViewing] = useState<Pick<TaskSetting, 'key' | 'label' | 'prompt_id'> | null>(null)
  const items = [{ key: 'scene-brief', label: 'Continuity brief', prompt_id: '' }, { key: 'scene-patch-check', label: 'Changed-passage check', prompt_id: '' }]
  return <details className="advanced-settings"><summary>Earlier workflow stages</summary><p className="subtle">These stages are retained for saved runs and original retries. New scenes read continuity directly and use your selection of the unified revision.</p>{items.map(task => <button className="text-button" key={task.key} onClick={() => setViewing(task)}>{task.label} instructions</button>)}{viewing && <TaskHistory task={viewing} onClose={() => setViewing(null)} />}</details>
}

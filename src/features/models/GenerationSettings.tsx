import { Field } from '../../components/Fields'
import { LocalThinking } from './LocalSettings'
import { temperatureCeiling } from './localProtocol'
import type { DiscoveredModel } from './discovery'
import type { ProfileConfig } from './types'

type Props = { config: ProfileConfig; patch: (next: Partial<ProfileConfig>) => void; model?: DiscoveredModel }
const samplerFields = [
  ['temperature', 'Temperature', 0, 2, .05], ['top_p', 'Top-p', 0, 1, .01], ['top_k', 'Top-k', 0, 1000, 1],
  ['min_p', 'Min-p', 0, 1, .01], ['frequency_penalty', 'Frequency penalty', -2, 2, .1],
  ['presence_penalty', 'Presence penalty', -2, 2, .1], ['repetition_penalty', 'Repetition penalty', .01, 3, .05], ['seed', 'Seed', 0, 2147483647, 1],
] as const

function samplingFields(config: ProfileConfig) {
  const { provider, local_protocol } = config
  if (provider === 'codex') return []
  if (provider === 'local' && local_protocol === 'lmstudio') return samplerFields.slice(0, 1)
  if (provider === 'openai') return samplerFields.slice(0, 2)
  if (provider === 'anthropic' || provider === 'google') return samplerFields.slice(0, 3)
  if (provider === 'kobold') return samplerFields.filter(item => ['temperature', 'top_p', 'top_k', 'repetition_penalty'].includes(item[0]))
  return samplerFields
}

export function GenerationSettings(props: Props) {
  const { config, patch } = props
  return <div className="form-stack"><BudgetControls {...props} /><ThinkingControls {...props} />
    {config.provider === 'openai' && <Choice label="Response verbosity" value={config.response_verbosity} options={['low', 'medium', 'high']} onChange={value => patch({ response_verbosity: value as ProfileConfig['response_verbosity'] })} />}
    <p className="subtle">Set preferred prose length in Story setup. A short prose request can still need a larger token allowance for thinking. Profile changes apply to new requests; “Retry original inputs” keeps the recorded limits.</p>
    <SamplingControls {...props} />
    <Field label="Timeout (seconds)" type="number" min={10} max={1800} value={config.timeout_seconds} onChange={event => patch({ timeout_seconds: Number(event.target.value) })} />
  </div>
}

function BudgetControls({ config, patch, model }: Props) {
  const cli = config.provider === 'codex', safety = config.context_safety_tokens ?? 0
  const input = config.context_tokens - config.max_output_tokens - safety
  return <><h3>Context and response space</h3>
    <Field label="Context allowance (tokens)" type="number" min={1024} max={2000000} value={config.context_tokens} onChange={event => patch({ context_tokens: Number(event.target.value) })} hint={model?.context_tokens ? `Provider reported ${model.context_tokens.toLocaleString()} tokens. This app budget can be lower.` : 'Model capacity is not reported. Set this to the model’s supported context size.'} />
    <Field label={cli ? 'Reserved output budget (tokens)' : 'Maximum output tokens'} type="number" min={64} max={128000} value={config.max_output_tokens} onChange={event => patch({ max_output_tokens: Number(event.target.value) })} hint={cli ? 'Used for context planning. The CLI controls its hard output limit.' : 'This is the total output allowance, including thinking where the provider counts it. It is not a prose-length target.'} />
    <Field label="Context safety margin (tokens)" type="number" min={0} max={100000} value={safety} onChange={event => patch({ context_safety_tokens: Number(event.target.value) })} hint="Reserve room for token-estimation differences and provider message framing." />
    <p className="subtle" role="status">{Math.max(0, input).toLocaleString()} tokens available for story inputs, before any long-story memory overhead.</p>
    {input <= 0 && <p role="alert">Increase context allowance or lower the output reservation and safety margin.</p>}
    <OutputLimitWarning config={config} model={model} />
  </>
}

function OutputLimitWarning({ config, model }: Pick<Props, 'config' | 'model'>) {
  if (!model?.max_output_tokens || config.max_output_tokens <= model.max_output_tokens) return null
  return <p role="alert">The output allowance exceeds the provider-reported maximum of {model.max_output_tokens.toLocaleString()} tokens.</p>
}

function ThinkingControls(props: Props) {
  const { config } = props, provider = config.provider
  const native = provider === 'local' && config.local_protocol === 'lmstudio'
  const compatible = provider === 'compatible' || (provider === 'local' && !native)
  return <><h3>Thinking controls</h3>
    {!native && provider !== 'kobold' && <EffortControl {...props} />}
    {['anthropic', 'google', 'openrouter'].includes(provider) && <ModeControl {...props} />}
    {config.thinking_mode === 'budget' && <ThinkingBudget {...props} />}
    {compatible && <CompatibleControls {...props} />}
    <LocalThinking {...props} />
    {provider === 'kobold' && <p className="subtle">The native Kobold adapter does not expose a thinking control.</p>}
  </>
}

function EffortControl({ config, patch, model }: Props) {
  const efforts = config.provider === 'google' ? ['minimal', 'low', 'medium', 'high'] : config.provider === 'anthropic' ? ['low', 'medium', 'high', 'xhigh', 'max'] : ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']
  const reported = model?.supported_efforts ?? config.reported_capabilities?.supported_efforts
  const available = reported ? efforts.filter(value => reported.includes(value)) : efforts
  return <Choice label="Reasoning effort" value={config.reasoning_effort} options={available} onChange={value => patch({ reasoning_effort: value, ...(config.provider === 'google' ? { thinking_mode: null, thinking_budget_tokens: null } : {}) })} hint={reported ? 'Options reported by the selected model.' : 'Adapter options; model support is unreported. Choose only values your model supports.'} />
}

function ModeControl({ config, patch }: Props) {
  const provider = config.provider
  const change = (value: string | null) => patch({
    thinking_mode: value as ProfileConfig['thinking_mode'],
    thinking_budget_tokens: value === 'budget' ? (provider === 'anthropic' ? 1024 : 512) : null,
    ...((provider === 'google' || value === 'off') ? { reasoning_effort: null } : {}),
  })
  return <Choice label="Thinking mode" value={config.thinking_mode} options={provider === 'google' ? ['off', 'budget'] : ['off', 'budget', 'adaptive']} onChange={change} hint={provider === 'anthropic' ? 'Use adaptive on models that support it; older thinking models use a budget. Clear temperature and top-k when thinking is enabled.' : 'Leave at default when support is unknown. Off is unavailable on some models.'} />
}

function ThinkingBudget({ config, patch }: Props) {
  const budget = config.thinking_budget_tokens ?? -1
  const response = budget >= 0 ? config.max_output_tokens - budget : null
  const reserve = config.response_reserve_tokens ?? 256
  return <><Field label="Thinking budget (tokens)" type="number" min={config.provider === 'anthropic' ? 1024 : config.provider === 'google' ? -1 : 0} max={128000} value={config.thinking_budget_tokens ?? ''} onChange={event => patch({ thinking_budget_tokens: event.target.value === '' ? null : Number(event.target.value) })} hint={config.provider === 'google' ? 'Use -1 for a dynamic budget, or 0 to turn thinking off where supported. Do not combine with effort.' : 'Leave enough of the total output allowance for the answer.'} />
    <Field label="Response space after thinking (tokens)" type="number" min={64} max={128000} value={reserve} onChange={event => patch({ response_reserve_tokens: Number(event.target.value) })} hint="A planning check, not a guarantee. The thinking budget plus this space must fit Maximum output tokens." />
    <ThinkingSpace response={response} reserve={reserve} />
  </>
}

function ThinkingSpace({ response, reserve }: { response: number | null; reserve: number }) {
  if (response === null) return null
  return <><p className="subtle" role="status">{response.toLocaleString()} output tokens remain after the thinking budget.</p>{response < reserve && <p role="alert">The thinking budget leaves too little room for a response. Lower it or increase Maximum output tokens.</p>}</>
}

function CompatibleControls({ config, patch }: Props) {
  const thinking = config.compatible_thinking == null ? null : config.compatible_thinking ? 'on' : 'off'
  return <><Choice label="Chat-template thinking" value={thinking} options={['off', 'on']} onChange={value => patch({ compatible_thinking: value === null ? null : value === 'on' })} hint="For servers and models supporting enable_thinking, including selected NIM and local models. Default sends no switch." />
    <Choice label="Output-limit parameter" value={config.output_token_parameter ?? 'max_tokens'} options={['max_tokens', 'max_completion_tokens']} noDefault onChange={value => patch({ output_token_parameter: value as ProfileConfig['output_token_parameter'] })} hint="Use max_completion_tokens only when your compatible model requires it." /></>
}

function SamplingControls({ config, patch }: Props) {
  return <details className="advanced-settings"><summary>Sampling settings</summary><div className="form-stack"><p className="subtle">Blank uses the model default. Support varies by model; some thinking models reject sampling controls.</p>
    {samplingFields(config).map(([key, label, min, max, step]) => <Field key={key} label={label} type="number" min={min} max={key === 'temperature' ? temperatureCeiling(config) : max} step={step} value={config[key] ?? ''} placeholder="Model default" onChange={event => patch({ [key]: event.target.value === '' ? null : Number(event.target.value) })} hint={config.reported_capabilities?.supported_parameters && !config.reported_capabilities.supported_parameters.includes(key) ? 'Not reported as supported by this model. Leave blank.' : undefined} />)}
    <button className="text-button" onClick={() => patch(Object.fromEntries(samplerFields.map(([key]) => [key, null])))}>Clear sampling overrides</button></div></details>
}

function Choice({ label, value, options, onChange, hint, noDefault }: { label: string; value?: string | null; options: string[]; onChange: (value: string | null) => void; hint?: string; noDefault?: boolean }) {
  return <label className="field"><span>{label}</span><select aria-label={label} value={value ?? ''} onChange={event => onChange(event.target.value || null)}>{!noDefault && <option value="">Model default</option>}{value && !options.includes(value) && <option value={value}>{value} · saved, not reported</option>}{options.map(option => <option key={option} value={option}>{option}</option>)}</select>{hint && <small>{hint}</small>}</label>
}

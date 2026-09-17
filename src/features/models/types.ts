export type Provider = 'openai' | 'anthropic' | 'openrouter' | 'local' | 'kobold' | 'codex' | 'google' | 'compatible'
export interface ProfileConfig {
  provider: Provider
  model: string
  base_url: string
  max_output_tokens: number
  context_tokens: number
  timeout_seconds: number
  temperature: number | null
  reasoning_effort: string | null
}
export interface ModelProfile {
  display_name?: string
  id: string
  profile_id: string
  number: number
  name: string
  config: ProfileConfig
  has_saved_key: boolean
}
export interface ProfileList { profiles: ModelProfile[]; primary_profile_id: string | null }
export const providers: Record<Provider, { name: string; url: string; description: string }> = {
  openai: { name: 'OpenAI', url: 'https://api.openai.com/v1', description: 'Connect with an OpenAI API key.' },
  anthropic: { name: 'Anthropic', url: 'https://api.anthropic.com/v1', description: 'Connect with an Anthropic API key.' },
  openrouter: { name: 'OpenRouter', url: 'https://openrouter.ai/api/v1', description: 'Choose a model through your OpenRouter account.' },
  google: { name: 'Google / Gemini', url: 'https://generativelanguage.googleapis.com/v1beta', description: 'Connect directly with a Google AI Studio / Gemini API key.' },
  compatible: { name: 'OAI Compatible API', url: '', description: 'Use an OpenAI-compatible Chat Completions API, including NanoGPT, DeepSeek, or NVIDIA NIM. Enter its API base URL.' },
  codex: { name: 'Codex / ChatGPT', url: '', description: 'Use your installed Codex CLI and its existing login. Sign in with codex login in your terminal.' },
  local: { name: 'Local / LM Studio', url: 'http://127.0.0.1:1234/v1', description: 'Connect to a local server with an OpenAI-compatible API, including LM Studio or Ollama.' },
  kobold: { name: 'Kobold', url: 'http://127.0.0.1:5001/api/v1', description: 'Connect to the native Kobold generation API on this device.' },
}
export const initialConfig: ProfileConfig = { provider: 'openai', model: '', base_url: providers.openai.url, max_output_tokens: 1200, context_tokens: 16000, timeout_seconds: 180, temperature: null, reasoning_effort: null }

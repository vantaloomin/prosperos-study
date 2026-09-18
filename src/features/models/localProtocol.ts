import type { LocalProtocol, ProfileConfig } from './types.ts'

export function localProtocolSettings(config: ProfileConfig, protocol: LocalProtocol): Partial<ProfileConfig> {
  const base = config.base_url.replace(/\/+$/, '')
  const host = base.replace(/\/(api\/)?v1$/, '')
  return { local_protocol: protocol, local_reasoning: null, reported_capabilities: null, reasoning_effort: null,
    compatible_thinking: null, output_token_parameter: 'max_tokens', top_p: null, top_k: null, min_p: null,
    frequency_penalty: null, presence_penalty: null, repetition_penalty: null, seed: null,
    base_url: host + (protocol === 'lmstudio' ? '/api/v1' : '/v1') }
}

export function localAddressHint(config: ProfileConfig): string {
  if (config.provider !== 'local') return 'Use the API base URL, without /models or /chat/completions.'
  return config.local_protocol === 'lmstudio'
    ? 'LM Studio native API: http://127.0.0.1:1234/api/v1. Test the connection to see supported thinking settings.'
    : 'OpenAI-compatible API: http://127.0.0.1:1234/v1. Include /v1, even when the server panel shows only the host and port.'
}

export const nativeLocal = (config: ProfileConfig) => config.provider === 'local' && config.local_protocol === 'lmstudio'
export const temperatureCeiling = (config: ProfileConfig) => nativeLocal(config) || config.provider === 'anthropic' ? 1 : 2

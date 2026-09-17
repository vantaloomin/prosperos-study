import assert from 'node:assert/strict'
import test from 'node:test'
import { discoveredSettings, typedModelSettings } from '../src/features/models/discovery.ts'
import { initialConfig } from '../src/features/models/types.ts'

const known = { id: 'known', name: 'Known model', context_tokens: 131072, max_output_tokens: 8192, limit_source: 'provider' }
const unknown = { id: 'unknown', name: 'Unknown model', context_tokens: null, max_output_tokens: null, limit_source: 'unreported' }
test('selecting a reported model preserves preferred output cost and caps unsupported output', () => {
  assert.equal(discoveredSettings(known, initialConfig).max_output_tokens, initialConfig.max_output_tokens)
  assert.equal(discoveredSettings(known, { ...initialConfig, max_output_tokens: 16000 }).max_output_tokens, 8192)
  assert.equal(discoveredSettings(known, initialConfig).context_tokens, 131072)
})
test('switching to an unreported or manually typed ID cannot inherit another models context ceiling', () => {
  const previous = { ...initialConfig, ...discoveredSettings(known, initialConfig) }
  assert.equal(discoveredSettings(unknown, previous).context_tokens, initialConfig.context_tokens)
  assert.equal(typedModelSettings('custom-model', previous, [known]).context_tokens, initialConfig.context_tokens)
  assert.equal(typedModelSettings('known', previous, [known]).context_tokens, 131072)
})


test('connection errors distinguish outdated app routes from provider failures', async () => {
  const { connectionError } = await import('../src/features/models/connectionErrors.ts')
  for (const status of [404, 405]) {
    const message = connectionError(Object.assign(new Error('Method Not Allowed'), { status }))
    assert.match(message, new RegExp(`POST /api/profiles/discover, HTTP ${status}`))
    assert.match(message, /launch.bat/)
    assert.match(message, /did not reach your model provider/)
  }
  const provider = Object.assign(new Error('GET http://localhost:1234/models returned HTTP 405. Include /v1.'), { status: 502 })
  assert.equal(connectionError(provider), provider.message)
})

test('browser transport and response errors point to the app server', async () => {
  const { connectionError } = await import('../src/features/models/connectionErrors.ts')
  assert.match(connectionError(new TypeError('Failed to fetch')), /browser could not reach/)
  assert.match(connectionError(new SyntaxError('Unexpected token')), /unreadable response/)
  assert.match(connectionError(null), /both running/)
})

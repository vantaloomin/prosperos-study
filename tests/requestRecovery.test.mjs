import test from 'node:test'
import assert from 'node:assert/strict'
import { recoverRequest } from '../src/features/generation/requestRecovery.ts'

const request = { kind: 'message', path: '/branches/a/messages', body: { operation_id: 'original-id', expected_revision: 3, text: 'Original text', role: 'ooc' } }

test('a lost mutation response is recovered by receipt without resubmitting text', async () => {
  let saved = null, writes = 0
  const transport = async (path, body) => {
    if (!body) return { kind: saved ? 'message' : null, result: saved }
    assert.equal(path, request.path)
    assert.deepEqual(body, request.body)
    writes++
    saved = { node_id: 'saved-node', branch_id: 'a' }
    throw new Error('Connection lost after commit')
  }
  await assert.rejects(recoverRequest(request, transport), /Connection lost/)
  assert.deepEqual(await recoverRequest(request, transport), saved)
  assert.equal(writes, 1)
})

test('an unreachable receipt lookup never triggers an automatic mutation', async () => {
  let writes = 0
  await assert.rejects(recoverRequest(request, async (_, body) => {
    if (body) writes++
    throw new Error('offline')
  }), /offline/)
  assert.equal(writes, 0)
})

test('a missing receipt replays the identical operation and rejects a mismatched kind', async () => {
  const submitted = []
  const result = await recoverRequest(request, async (_, body) => {
    if (!body) return { kind: null, result: null }
    submitted.push(body)
    return { node_id: 'new-node' }
  })
  assert.deepEqual(result, { node_id: 'new-node' })
  assert.deepEqual(submitted, [request.body])
  await assert.rejects(recoverRequest(request, async () => ({ kind: 'generate', result: { id: 'wrong' } })), /different operation/)
})

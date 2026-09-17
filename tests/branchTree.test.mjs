import assert from 'node:assert/strict'
import test from 'node:test'
import { branchRows, nextBranchIndex } from '../src/features/chat/branchTree.ts'

test('a 10,000-generation tree is iterative and preserves exact ancestry', () => {
  const branches = Array.from({ length: 10001 }, (_, index) => ({ id: String(index), name: `Path ${index}`, forked_from: index ? String(index - 1) : null }))
  const rows = branchRows(branches.reverse())
  assert.equal(rows.length, 10001)
  assert.equal(rows[10000].depth, 10000)
  assert.equal(rows[10000].parentName, 'Path 9999')
  assert.equal(nextBranchIndex('ArrowLeft', 10000, rows), 9999)
  assert.equal(nextBranchIndex('ArrowRight', 9999, rows), 10000)
  assert.equal(nextBranchIndex('Home', 10000, rows), 0)
})

test('wide cousins keep sibling position independent of depth-first row number', () => {
  const rows = branchRows([
    { id: 'root', name: 'Root', forked_from: null },
    { id: 'one', name: 'One', forked_from: 'root' },
    { id: 'two', name: 'Two', forked_from: 'root' },
    { id: 'leaf', name: 'Leaf', forked_from: 'one' },
  ])
  assert.deepEqual(rows.map((row) => row.branch.id), ['root', 'one', 'leaf', 'two'])
  assert.deepEqual(rows.map((row) => [row.depth, row.position, row.siblings]), [[0, 1, 1], [1, 1, 2], [2, 1, 1], [1, 2, 2]])
  assert.equal(nextBranchIndex('ArrowLeft', 3, rows), 0)
  assert.equal(nextBranchIndex('End', 0, rows), 3)
})

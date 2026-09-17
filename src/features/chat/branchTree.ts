import type { BranchSummary } from '../../types'

export interface BranchRow { branch: BranchSummary; depth: number; parentName: string; position: number; siblings: number }

/** Iterative traversal: nesting never consumes the JavaScript call stack. */
export function branchRows(branches: BranchSummary[]): BranchRow[] {
  const byId = new Map(branches.map((branch) => [branch.id, branch]))
  const children = new Map<string, BranchSummary[]>()
  for (const branch of branches) {
    const parent = branch.forked_from ?? ''
    const siblings = children.get(parent) ?? []
    siblings.push(branch)
    children.set(parent, siblings)
  }
  const roots = branches.filter((branch) => !byId.has(branch.forked_from ?? ''))
  const stack = roots.map((branch, index) => ({ branch, depth: 0, parentName: '', position: index + 1, siblings: roots.length })).reverse()
  const result: BranchRow[] = []
  const visited = new Set<string>()
  while (stack.length) {
    const row = stack.pop()!
    if (visited.has(row.branch.id)) continue
    visited.add(row.branch.id)
    result.push(row)
    const descendants = children.get(row.branch.id) ?? []
    for (let index = descendants.length - 1; index >= 0; index -= 1) {
      stack.push({ branch: descendants[index], depth: row.depth + 1, parentName: row.branch.name, position: index + 1, siblings: descendants.length })
    }
  }
  return result
}

export function nextBranchIndex(key: string, current: number, rows: BranchRow[]) {
  if (key === 'Home') return 0
  if (key === 'End') return rows.length - 1
  if (key === 'ArrowUp') return Math.max(0, current - 1)
  if (key === 'ArrowDown') return Math.min(rows.length - 1, current + 1)
  if (key === 'ArrowLeft') return rows.findIndex((row) => row.branch.id === rows[current]?.branch.forked_from)
  if (key === 'ArrowRight') return rows.findIndex((row) => row.branch.forked_from === rows[current]?.branch.id)
  return -1
}

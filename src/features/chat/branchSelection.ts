import type { Story } from '../../types'

export function resolveBranch(selected: string, story: Story | undefined) {
  return selected || story?.branches.find(branch => !branch.curation?.archived)?.id || story?.branches[0]?.id || ''
}

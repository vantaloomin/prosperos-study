import type { Role } from '../../types'

export type StoryMode = 'directed' | 'scene' | 'roleplay'

export function storyMode(settings: Record<string, unknown>): StoryMode {
  return settings.experience === 'directed' || settings.experience === 'scene' ? settings.experience : 'roleplay'
}

const roleplayLabels: Record<Role, string> = { user: 'You', assistant: 'Character', narrator: 'Narration', ooc: 'Out of character' }
const writingLabels: Record<Role, string> = { user: 'Character contribution', assistant: 'Story text', narrator: 'Story text', ooc: "Author’s note" }
export const messageLabels = (mode: StoryMode) => mode === 'roleplay' ? roleplayLabels : writingLabels

export function composerOptions(mode: StoryMode): [Role, string][] {
  return mode === 'roleplay'
    ? [['user', 'Your character'], ['narrator', 'Narration'], ['assistant', 'Other character'], ['ooc', 'Out of character']]
    : [['narrator', 'Story text'], ['ooc', 'Author’s note'], ['user', 'Character dialogue'], ['assistant', 'Other character']]
}

export function composerRole(saved: unknown, legacyDraft: boolean, mode: StoryMode): Role {
  if (saved === 'user' || saved === 'assistant' || saved === 'narrator' || saved === 'ooc') return saved
  if (legacyDraft || mode === 'roleplay') return 'user'
  return 'narrator'
}

export function composerCopy(mode: StoryMode, role: Role) {
  if (mode === 'roleplay') return { placeholder: 'What happens next?', submit: 'Add message', caption: 'Saved on this device · Manual writing' }
  if (role === 'ooc') return { placeholder: 'Leave direction for the next draft…', submit: 'Add author’s note', caption: 'Instructions at this point on this path. They stay in future context until removed; they are not story events.' }
  return { placeholder: 'Write the next passage…', submit: 'Add passage', caption: 'Saved on this device · Your words, added to this path' }
}

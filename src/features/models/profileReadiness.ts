import type { ProfileConfig, ProfileList } from './types'

export const profileReady = (config: ProfileConfig) => !!config.model.trim() && (config.provider === 'codex' || !!config.base_url.trim())
export function readyProfiles(data: ProfileList): ProfileList {
  const profiles = data.profiles.filter(profile => profileReady(profile.config))
  return { profiles, primary_profile_id: profiles.some(profile => profile.profile_id === data.primary_profile_id) ? data.primary_profile_id : null }
}

export function profileSaveState(config: ProfileConfig, key: string, initial: { config: ProfileConfig; savedKey: boolean }) {
  const ready = profileReady(config)
  const savedKey = initial.config.provider === config.provider && (!initial.config.base_url || initial.config.base_url === config.base_url) && initial.savedKey
  return { ready, savedKey, canSave: ready || !!key.trim() || savedKey }
}

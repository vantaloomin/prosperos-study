import type { ActorInput, DialogueSetup } from './CharacterDialogue'

export function actorInputs(setup: DialogueSetup): ActorInput[] {
  if (!setup.enabled) return []
  return setup.actors.map(actor => ({ slot_ids: actor.slot_ids, briefing: actor.briefing,
    ...(actor.view.startsWith('character:') ? { character_id: actor.view.slice(10) } : { subject: actor.view.slice(5) }) }))
}

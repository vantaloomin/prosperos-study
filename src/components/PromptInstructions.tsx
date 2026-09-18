export interface PromptSection { id: string; key: string; template: string; user_character: string }

export function PromptInstructions({ snapshot }: { snapshot: { prompt: { template: string }; prompt_sections?: PromptSection[] } }) {
  const mode = snapshot.prompt_sections?.filter(item => item.key.startsWith('section:mode-')) ?? []
  const agency = snapshot.prompt_sections?.filter(item => item.key.startsWith('section:agency-')) ?? []
  return <><h4>System instructions in request order</h4>{mode.map(section => <pre key={section.id}>{section.template}</pre>)}<pre>{snapshot.prompt.template}</pre>{agency.map(section => <pre key={section.id}>{section.template}</pre>)}</>
}

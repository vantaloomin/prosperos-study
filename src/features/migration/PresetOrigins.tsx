import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { PresetDownloads } from './PresetDownloads'
import { showValue } from './presetTypes'

interface Origin {
  import_id: string; filename: string
  receipt: { name: string; instructions: string; instruction_keys: string[]; sampling_keys: string[]; base_profile_name: string; configuration_changes: { field: string; before: unknown; after: unknown }[] }
}

export function PresetOrigins({ versionId }: { versionId: string }) {
  const query = useQuery({ queryKey: ['preset-origins', versionId], queryFn: () => api<Origin[]>(`/writing-versions/${versionId}/imports`) })
  return <><ErrorNotice message={query.error?.message} />{query.data?.map(origin => <details key={origin.import_id} className="import-compatibility"><summary>Imported preset source · {origin.filename}</summary><PresetDownloads id={origin.import_id} /><p>Reviewed recipe: {origin.receipt.name}. The original remains available even after newer recipe versions are published.</p><pre className="migration-prose">{origin.receipt.instructions || 'No source instructions were accepted.'}</pre><p>Selected source fragments: {origin.receipt.instruction_keys.join(', ') || 'None'}</p>{!!origin.receipt.configuration_changes.length && <><p>Separate profile based on {origin.receipt.base_profile_name}:</p><ul>{origin.receipt.configuration_changes.map(item => <li key={item.field}>{item.field}: {showValue(item.before)} → {showValue(item.after)}</li>)}</ul></>}</details>)}</>
}

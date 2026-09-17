import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { AssetVersion } from '../../types'
import { useReferences } from './versionQueries'
import { VersionSelect } from './VersionSelect'

function useLoreChoices(value: string[]) {
  const cache = useQueryClient()
  const books = useQuery({ queryKey: ['library'], queryFn: () => api<AssetVersion[]>('/library') })
  const references = useReferences(value)
  const known = [...(references.data ?? []), ...(books.data ?? []).flatMap((book) => [book, ...(cache.getQueryData<AssetVersion[]>(['versions', book.asset_id]) ?? [])])]
  const missing = value.some((id) => !known.some((item) => item.id === id))
  return { books, references, known, pending: books.isPending || (missing && references.isPending) }
}

export function LoreLinks({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const { books, references, known, pending } = useLoreChoices(value)
  if (pending) return <Loading label="Opening linked Canon collections…" />
  return <section className="lore-links"><h4>Linked Canon collections</h4><p className="subtle">Choose exact versions. Updates to these links are included in the Story update preview.</p>
    <ErrorNotice message={books.error?.message ?? references.error?.message} />
    {books.data?.filter((book) => book.kind === 'lorebook').map((book) => {
      const selected = known.find((item) => item.asset_id === book.asset_id && value.includes(item.id))
      return <div className="lore-link" key={book.asset_id}><label className="check-row"><input type="checkbox" checked={!!selected} disabled={!!references.error} onChange={(event) => onChange(event.target.checked ? [...value, book.id] : value.filter((id) => id !== selected?.id))} />{book.name}</label>
        {selected && <VersionSelect assetId={book.asset_id} name={book.name} value={selected.id} onChange={(id) => onChange(value.map((old) => old === selected.id ? id : old))} />}
      </div>
    })}
    {books.data?.every((book) => book.kind !== 'lorebook') && <p className="subtle">Create a Canon collection in the Library to link it here.</p>}
  </section>
}

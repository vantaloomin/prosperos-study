import { ErrorNotice } from '../../components/Feedback'
import { useVersions } from './versionQueries'

export function VersionSelect({ assetId, name, value, onChange, disabled = false, focusOnReady = false }: { assetId: string; name: string; value: string; onChange: (value: string) => void; disabled?: boolean; focusOnReady?: boolean }) {
  const query = useVersions(assetId)
  const control = useRef<HTMLSelectElement>(null)
  useEffect(() => {
    if (!focusOnReady || query.isPending) return
    const frame = requestAnimationFrame(() => control.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [focusOnReady, query.isPending])
  return <div className="version-select"><select ref={control} aria-label={`Version of ${name}`} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled || query.isPending || !!query.error}>
    {query.isPending && <option value={value}>Loading versions…</option>}
    {query.data?.map((version, index) => <option key={version.id} value={version.id}>v{version.number}{index === 0 ? ' · latest' : ''}{version.note ? ` · ${version.note}` : ''}</option>)}
  </select><ErrorNotice message={query.error?.message} /></div>
}
import { useEffect, useRef } from 'react'

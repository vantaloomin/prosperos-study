export function PresetDownloads({ id }: { id: string }) {
  return <div className="import-downloads"><a className="text-button" href={`/api/migration/presets/${id}/original`} download>Download original preset</a><a className="text-button" href={`/api/migration/presets/${id}/report`} download>Download preset report</a></div>
}

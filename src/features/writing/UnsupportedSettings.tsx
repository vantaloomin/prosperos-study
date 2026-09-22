export function UnsupportedSettings({ value }: { value?: Record<string, unknown> }) {
  if (!value || Object.keys(value).length === 0) return null
  return <details className="advanced-settings writing-unsupported"><summary>Retained settings · not applied ({Object.keys(value).length})</summary><p className="subtle">These imported settings are not supported here. They stay with this version for copying and export; they do not enter model instructions or activate tasks.</p><pre className="writing-json">{JSON.stringify(value, null, 2)}</pre></details>
}

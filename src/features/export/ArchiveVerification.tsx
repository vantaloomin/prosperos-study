export interface WriterVerification {
  checked: number
  complete: number
  limited: number
  limitations: string[]
}

export function ArchiveVerification({ result }: { result?: WriterVerification | null }) {
  if (!result?.checked) return null
  return <section className="archive-verification form-stack" aria-label="Writer memory source check">
    <h4>Writer memory source check</h4>
    {result.complete > 0 && <p>{result.complete.toLocaleString()} saved writer {result.complete === 1 ? 'input matched its' : 'inputs matched their'} archived prose and Canon sources.</p>}
    {result.limited > 0 && <><p>{result.limited.toLocaleString()} saved writer {result.limited === 1 ? 'input has' : 'inputs have'} limited verification. Saved text remains available to restore.</p><ul>{result.limitations.map((limit) => <li key={limit}>{limit}</li>)}</ul></>}
    <small>This checks saved source evidence. It does not rate retrieval relevance or the quality of generated writing.</small>
  </section>
}

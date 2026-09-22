import { ErrorNotice, Loading } from '../../components/Feedback'
import type { useRecipeOperation } from './useRecipeOperation'

export function RecipePending({ operation }: { operation: ReturnType<typeof useRecipeOperation> }) {
  return <section className="request-recovery form-stack" aria-label="Recipe request recovery"><p role="status">{operation.receipt.data ? 'The action is saved. Opening its recorded result…' : 'Checking the saved recipe action. Reopening this view does not send it again.'}</p>{operation.busy && <Loading label="Saving the requested recipe action…" />}<ErrorNotice message={operation.error || operation.receipt.error?.message} />{!operation.busy && !operation.receipt.data && <><button className="button" onClick={() => void operation.receipt.refetch()}>Check saved recipe action</button>{operation.receipt.isSuccess && <button className="button" onClick={() => void operation.retry()}>Retry the same saved action</button>}{operation.pending?.rejected && <button className="text-button" onClick={operation.clear}>Return to options after refusal</button>}</>}</section>
}

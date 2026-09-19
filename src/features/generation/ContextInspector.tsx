import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { MemoryCoverage } from './MemoryCoverage'
import { ContextBudgetView } from './ContextBudgetView'
import { ContextSectionView } from './ContextSectionView'
import type { ContextReport, ContextRequest } from './contextTypes'
import '../../styles/context-inspector.css'

interface Props { branchId: string; request: ContextRequest; onClose: () => void; onReviewed?: (fingerprint: string) => void }

export default function ContextInspector({ branchId, request, onClose, onReviewed }: Props) {
  const query = useQuery({ queryKey: ['context-preview', branchId, request],
    queryFn: () => api<ContextReport>(`/branches/${branchId}/context-preview`, request),
    retry: false, refetchOnWindowFocus: false, gcTime: 0 })
  return <Modal open onClose={onClose} title="What the writer will receive" description="Inspect the selected path and pinned sources before requesting a draft." wide>
    <div className="dialog-body form-stack context-inspector"><p className="subtle">This is a preview of the saved story. Unsent composer text is excluded. Opening it makes no model request and draws no randomness.</p>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Assembling the current inputs…" />}
      {query.data && !query.error && <ReportView key={query.data.fingerprint} report={query.data} branchId={branchId} request={request} />}
    </div><footer className="dialog-footer"><span className="subtle">Use this preview to check that the inputs still match before the next manual draft.</span><button className="button quiet" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? 'Checking…' : 'Refresh preview'}</button><button className="button quiet" onClick={onClose}>Done</button>{onReviewed && <button className="button primary" disabled={!usablePreview(query.data) || query.isFetching || !!query.error} onClick={() => { onReviewed(query.data!.fingerprint); onClose() }}>Use this preview</button>}</footer>
  </Modal>
}

function ReportView({ report, branchId, request }: { report: ContextReport; branchId: string; request: ContextRequest }) {
  return <><MemoryCoverage report={report} />
    {report.writer_recall && <p className="context-budget-warning">Prewriting recall is enabled. These are the initial inputs. Each candidate may make one preparation request, search earlier accepted prose, and replace optional excerpts within the same input allowance. Candidates may receive different evidence. Inspect each draft’s recall receipt for its final writer input. Using this preview protects the starting inputs and permitted search sources.</p>}
    {!!report.writer_recall?.available_groups && <p className="subtle">{report.writer_recall.available_groups} recorded evidence group(s) are available for discovery. Relevant groups can retrieve linked originals; the final receipt identifies missing members and incomplete coverage.</p>}
    {report.writer_recall?.semantic_enabled && <p className="subtle">Semantic recall is enabled: each candidate can add up to five embedding requests and 30 seconds using its configured embedding model. Its receipt records cache coverage, calls and fallback. The context allowance stays the same.</p>}
    {!!report.writer_recall?.relationship_annotations && <p className="subtle">{report.writer_recall.relationship_annotations} tentative relationship annotation(s) are frozen for discovery. Their original passages can be retrieved; the interpretations do not become accepted facts.</p>}
    <div className="context-budgets">{report.budgets.map((budget) => <ContextBudgetView key={budget.version_id} budget={budget} />)}</div>
    <p className="subtle">Input estimates use UTF-8 bytes ÷ 3, rounded up. They include instructions, all serialized context and record metadata. Section estimates sum to the input total. The configured limit is not a measured model capacity; provider tokenization, chat framing and CLI instructions can add overhead.</p>
    <AssessmentNotice assessment={report.assessment} />
    <div className="context-section-list"><h3>Included sources</h3><p className="subtle">{report.knowledge_lens ? "Inspect the permitted evidence and instructions for this character. Omitted material is not supplied to the writer." : "Open a section to read its inputs. Private background and prepared beats may reveal future story material."}</p>
      {report.sections.map((section) => <ContextSectionView key={section.key} branchId={branchId} request={request} fingerprint={report.fingerprint} section={section} />)}</div>
    <ReferenceScope character={Boolean(report.knowledge_lens)} /></>
}

function AssessmentNotice({ assessment }: { assessment: ContextReport['assessment'] }) {
  return assessment.status === 'completed' ? <p className="subtle">A ready beat is included in these exact inputs. Writing makes no additional assessment request.</p> : null
}

function usablePreview(report?: ContextReport) {
  return !!report && report.budgets.every(budget => budget.fits)
}

function ReferenceScope({ character }: { character: boolean }) {
  return <p className="subtle">{character ? 'This character view uses only explicitly granted prose and pinned reference excerpts. Other Canon, Character fields and free-text Story preferences are not shared automatically. Writing mode and character agency are preserved.' : 'Library sources use the versions pinned to this branch. Later Markdown edits do not enter this request until a new version is published and adopted. Full original imports remain available in Library.'}</p>
}

import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { ContextBudgetView } from './ContextBudgetView'
import { ContextSectionView } from './ContextSectionView'
import type { ContextReport, ContextRequest } from './contextTypes'
import '../../styles/context-inspector.css'

interface Props { branchId: string; request: ContextRequest; onClose: () => void }

export default function ContextInspector({ branchId, request, onClose }: Props) {
  const query = useQuery({ queryKey: ['context-preview', branchId, request],
    queryFn: () => api<ContextReport>(`/branches/${branchId}/context-preview`, request),
    retry: false, refetchOnWindowFocus: false, gcTime: 0 })
  return <Modal open onClose={onClose} title="What the writer will receive" description="Inspect the selected path and pinned sources before requesting a draft." wide>
    <div className="dialog-body form-stack context-inspector"><p className="subtle">This is a preview of the saved story. Unsent composer text is excluded. Opening it makes no model request and draws no randomness.</p>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Assembling the current inputs…" />}
      {query.data && !query.error && <ReportView key={query.data.fingerprint} report={query.data} branchId={branchId} request={request} />}
    </div><footer className="dialog-footer"><span className="subtle">Generation checks the inputs again before sending.</span><button className="button quiet" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? 'Checking…' : 'Refresh preview'}</button><button className="button primary" onClick={onClose}>Done</button></footer>
  </Modal>
}

function ReportView({ report, branchId, request }: { report: ContextReport; branchId: string; request: ContextRequest }) {
  return <><div className="context-coverage"><span>Complete selected path · {report.coverage.messages.toLocaleString()} contributions</span><small>Branch revision {report.branch_revision} · Story revision {report.story_revision} · Writer prompt v{report.prompt_version}</small></div>
    <div className="context-budgets">{report.budgets.map((budget) => <ContextBudgetView key={budget.version_id} budget={budget} />)}</div>
    <p className="subtle">Input estimates use UTF-8 bytes ÷ 3, rounded up. They include instructions, all serialized context and record metadata. Section estimates sum to the input total. The configured limit is not a measured model capacity; provider tokenization, chat framing and CLI instructions can add overhead.</p>
    <AssessmentNotice assessment={report.assessment} />
    <div className="context-section-list"><h3>Included sources</h3><p className="subtle">Open a section to read its inputs. Private background and prepared beats may reveal future story material.</p>
      {report.sections.map((section) => <ContextSectionView key={section.key} branchId={branchId} request={request} fingerprint={report.fingerprint} section={section} />)}</div>
    <p className="subtle">Library sources use the versions pinned to this branch. Later Markdown edits do not enter this request until a new version is published and adopted. Full original imports remain available in Library.</p></>
}

function AssessmentNotice({ assessment }: { assessment: ContextReport['assessment'] }) {
  if (assessment.status === 'saved') return <p className="context-budget-warning">A beat assessment is already saved here. Reopen it from the story before proceeding; its frozen inputs and choices govern continuation. This shows the current prospective writer context.</p>
  if (assessment.status !== 'new') return null
  return <details className="context-assessment"><summary>Beat assessment comes first · {assessment.budgets.length} additional request(s)</summary>
    <p className="subtle">These checks use their own inputs and exclude private background. Their result may add a prepared beat or change selected lore, so the final writer input will be checked again. No assessment is started by this preview.</p>
    {assessment.budgets.map((budget) => <ContextBudgetView key={budget.version_id} budget={budget} />)}</details>
}

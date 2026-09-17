import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { LoreReceiptView, type LoreReceipt } from './LoreReceiptView'

export function LoreInspection({ branchId, onClose }: { branchId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['lore-inspection', branchId], queryFn: () => api<{ current: LoreReceipt; prepared: LoreReceipt | null; notice: string }>(`/branches/${branchId}/lore`), staleTime: 0 })
  return <Modal open wide title="Lore on this path" description="Inspect the selected path’s pinned books, matching rules and saved chance decisions." onClose={onClose}>
    <div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
      {query.data && <><p className="subtle">{query.data.notice}</p><LoreReceiptView receipt={query.data.current} label="Current accepted path" />{query.data.prepared && <LoreReceiptView receipt={query.data.prepared} label="Prepared beat · not yet accepted" />}</>}
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer>
  </Modal>
}

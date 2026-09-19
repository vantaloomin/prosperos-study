export interface RecallReceiptData {
  status: 'preparing' | 'cancelled' | 'completed' | 'fallback'
  queries?: string[]
  decisions?: { id: string; source_id: string; passage_number?: number; fate: string }[]
  groups?: RecallGroup[]
  omitted_group_ids?: string[]
  semantic?: SemanticReceiptData
  displaced_ids?: string[]
  calls: number
  seconds?: number
  reason?: string
  final_input?: { content: string; estimated_input_tokens: number }
}

export function RecallReceipt({ receipt }: { receipt?: RecallReceiptData }) {
  if (!receipt) return null
  return <details className="request-details recall-receipt"><summary>Prewriting recall · {receipt.status}</summary>
    {receipt.reason && <p>{receipt.reason}</p>}
    <PreparationCost receipt={receipt} />
    <SemanticReceipt receipt={receipt.semantic} />
    {!!receipt.queries?.length && <ul>{receipt.queries.map(query => <li key={query}>{query}</li>)}</ul>}
    <GroupCoverage groups={receipt.groups} omitted={receipt.omitted_group_ids?.length ?? 0} />
    <RecallDecisions decisions={receipt.decisions} />
    {!!receipt.displaced_ids?.length && <p>{receipt.displaced_ids.length} optional passage(s) replaced to fit the input allowance.</p>}
    {receipt.final_input && <details><summary>Exact final writer context · about {receipt.final_input.estimated_input_tokens.toLocaleString()} input tokens including instructions</summary><pre>{receipt.final_input.content}</pre></details>}
  </details>
}

interface SemanticReceiptData {
  status: string; calls: number; seconds?: number; reason?: string; cache_hits: number; new_sources: number; total_sources: number
  identity: { model: string }; actual_model?: string
}

function SemanticReceipt({ receipt }: { receipt?: SemanticReceiptData }) {
  if (!receipt) return null
  return <div><p>Semantic search · {receipt.status} · {receipt.calls} embedding request(s){receipt.seconds !== undefined && ` · ${receipt.seconds.toFixed(1)}s`}</p>
    <p className="subtle">Model: {receipt.actual_model || receipt.identity.model || 'not configured'}. {receipt.cache_hits} cached and {receipt.new_sources} newly prepared of {receipt.total_sources} permitted passages. Preparation time above includes this step. Keyword search remains independent.</p>
    {receipt.reason && <p>{receipt.reason}</p>}
  </div>
}

function PreparationCost({ receipt }: { receipt: RecallReceiptData }) {
  return <p className="subtle">Saved preparation: {receipt.calls} request(s){receipt.seconds !== undefined ? ` · ${receipt.seconds.toFixed(1)}s` : ''}. Completed preparation is reused on retry. Only exact accepted passages can be added. Search results do not establish that every relevant event was found or that a character knows it.</p>
}

function RecallDecisions({ decisions = [] }: { decisions?: RecallReceiptData['decisions'] }) {
  if (!decisions.length) return null
  return <ul>{decisions.map(item => <li key={item.id} title={item.id}>{item.passage_number ? `Passage ${item.passage_number}` : item.source_id} · {item.fate}</li>)}</ul>
}

interface RecallGroup {
  id: string; label: string; kind: string; member_ids: string[]; supplied_ids: string[]; missing_ids: string[]
  unavailable_evidence: number; omitted_members: number; complete: boolean
}

function GroupCoverage({ groups = [], omitted }: { groups?: RecallGroup[]; omitted: number }) {
  if (!groups.length && !omitted) return null
  return <div className="recall-group-coverage"><p>Linked evidence coverage. “Complete” refers only to recorded members; unrecorded relationships may still be missing.</p>
    <ul>{groups.map(group => <li key={group.id}><strong>{group.label}</strong> · {group.complete ? 'Complete recorded group' : 'Partial recorded group'}<br />
      {group.supplied_ids.length} of {group.member_ids.length + group.omitted_members} original passages supplied · {group.kind}
      {group.unavailable_evidence > 0 && <small> · {group.unavailable_evidence} evidence reference(s) unavailable in this search scope</small>}
    </li>)}</ul>
    {omitted > 0 && <p>{omitted} group(s) could not fit their coverage note and were omitted from group expansion.</p>}
  </div>
}

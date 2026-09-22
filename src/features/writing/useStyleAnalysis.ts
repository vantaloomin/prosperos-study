import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { analysisWorking, type AnalysisJob } from './analysisTypes'

export function useAnalysis(id: string | null) {
  return useQuery({ queryKey: ['style-analysis', id], queryFn: () => api<AnalysisJob>(`/writing-analyses/${id}`), enabled: !!id,
    refetchInterval: query => analysisWorking(query.state.data?.status) ? 1000 : false })
}

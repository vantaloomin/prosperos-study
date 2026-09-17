import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import type { ModelProfile, ProfileConfig } from './types'
import type { Discovery } from './discovery'
import { connectionError } from './connectionErrors'

function probeBody(config: ProfileConfig, key: string, profile?: ModelProfile) {
  return { config, api_key: key || null, profile_id: profile?.profile_id ?? null, expected_version_id: profile?.id ?? null }
}

export function useModelDiscovery(profile?: ModelProfile) {
  const [result, setResult] = useState<Discovery | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sequence = useRef(0)
  useEffect(() => () => { sequence.current++ }, [])
  const reset = () => { sequence.current++; setResult(null); setError(''); setBusy(false) }
  const connect = async (config: ProfileConfig, key: string, onResult: (value: Discovery) => void) => {
    const request = ++sequence.current
    setBusy(true); setError(''); setResult(null)
    try {
      const value = await api<Discovery>('/profiles/discover', probeBody(config, key, profile))
      if (request !== sequence.current) return
      setResult(value); onResult(value)
    } catch (failure) {
      if (request === sequence.current) setError(connectionError(failure))
    } finally { if (request === sequence.current) setBusy(false) }
  }
  return { result, busy, error, reset, connect }
}

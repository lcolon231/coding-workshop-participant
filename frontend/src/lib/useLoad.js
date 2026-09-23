import { useEffect, useState } from 'react'

/**
 * Load something, keep the last answer while a retry is in flight, and
 * start blank when the loader itself changes (a different parent selected).
 *
 * `load` must be memoised: its identity is the cache key. `enabled` false
 * means there is nothing to load yet, for a child list with no parent.
 */
export function useLoad(load, enabled = true) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ load: null, attempt: -1, data: null, error: null })

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    load()
      .then((data) => {
        if (!cancelled) setState({ load, attempt, data, error: null })
      })
      .catch((err) => {
        if (!cancelled) setState((current) => ({ load, attempt, data: current.data, error: err.message }))
      })
    return () => {
      cancelled = true
    }
  }, [load, attempt, enabled])

  const fresh = state.load === load
  const loading = enabled && !(fresh && state.attempt === attempt)
  return {
    data: enabled && fresh ? state.data : null,
    error: !loading && fresh ? state.error : null,
    loading,
    reload: () => setAttempt((n) => n + 1),
  }
}

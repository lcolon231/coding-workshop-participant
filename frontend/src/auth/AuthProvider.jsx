import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../services/api'
import { fetchMe, logout } from '../services/auth'
import { clearSession, readSession, subscribeSession } from '../services/session'
import { AuthContext } from './AuthContext'

function initialState() {
  return readSession() ? { status: 'loading', user: null, error: null } : ANONYMOUS
}

const ANONYMOUS = { status: 'anonymous', user: null, error: null }

/**
 * Knows who is signed in.
 *
 * Reads `/api/auth/me` whenever a session appears, so the role and name come
 * from the server rather than from anything decoded on the client. A session
 * that the API rejects is cleared, which sends every protected route to the
 * sign-in screen.
 */
export default function AuthProvider({ children }) {
  const [state, setState] = useState(initialState)

  useEffect(() => {
    if (state.status !== 'loading') return undefined
    let cancelled = false
    fetchMe()
      .then((user) => {
        if (!cancelled) setState({ status: 'signed-in', user, error: null })
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          clearSession()
        } else {
          setState({ status: 'error', user: null, error: err.message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [state.status])

  useEffect(
    () =>
      subscribeSession((session) => {
        if (!session) {
          setState(ANONYMOUS)
        } else {
          // A rotation keeps the user; a fresh sign-in has to load them.
          setState((current) =>
            current.user ? current : { status: 'loading', user: null, error: null },
          )
        }
      }),
    [],
  )

  const signOut = useCallback(() => {
    const session = readSession()
    clearSession()
    if (session?.refreshToken) {
      // Best effort: the local session is already gone either way.
      logout(session.refreshToken).catch(() => {})
    }
  }, [])

  const retry = useCallback(() => {
    setState(readSession() ? { status: 'loading', user: null, error: null } : ANONYMOUS)
  }, [])

  const value = useMemo(() => ({ ...state, signOut, retry }), [state, signOut, retry])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

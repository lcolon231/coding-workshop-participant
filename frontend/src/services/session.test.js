import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearSession, readSession, saveSession, subscribeSession } from './session'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('session', () => {
  it('stores a token pair with its expiry and reads it back', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    const session = saveSession({ access_token: 'a', refresh_token: 'r', expires_in: 60 })

    expect(session).toEqual({ accessToken: 'a', refreshToken: 'r', expiresAt: 1_060_000 })
    expect(readSession()).toEqual(session)
  })

  it('tells subscribers on save and on clear, until they unsubscribe', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeSession(listener)

    saveSession({ access_token: 'a', refresh_token: 'r', expires_in: 60 })
    expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({ accessToken: 'a' }))
    clearSession()
    expect(listener).toHaveBeenLastCalledWith(null)

    unsubscribe()
    saveSession({ access_token: 'b', refresh_token: 'r', expires_in: 60 })
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('survives storage that throws: the session is returned to the caller, not persisted', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    const listener = vi.fn()
    subscribeSession(listener)

    const session = saveSession({ access_token: 'a', refresh_token: 'r', expires_in: 60 })
    expect(session.accessToken).toBe('a')
    expect(() => clearSession()).not.toThrow()
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('reads null when the stored value is not JSON', () => {
    sessionStorage.setItem('acme.session', '{not json')
    expect(readSession()).toBeNull()
  })
})

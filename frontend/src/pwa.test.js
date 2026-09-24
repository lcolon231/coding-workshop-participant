import { afterEach, describe, expect, it, vi } from 'vitest'
import { registerServiceWorker } from './pwa'

/** The `load` listener the call installed, if any; never dispatched for real, so tests stay isolated. */
function installedLoadListener() {
  const listen = vi.spyOn(window, 'addEventListener')
  registerServiceWorker()
  const call = listen.mock.calls.find(([type]) => type === 'load')
  return call ? call[1] : null
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('registerServiceWorker', () => {
  it('registers the offline shell after load in a production build, and swallows a refusal', async () => {
    vi.stubEnv('PROD', true)
    const register = vi.fn().mockRejectedValue(new Error('insecure origin'))
    vi.stubGlobal('navigator', { serviceWorker: { register } })

    const onLoad = installedLoadListener()
    expect(onLoad).toBeTypeOf('function')
    expect(register).not.toHaveBeenCalled()

    onLoad()
    expect(register).toHaveBeenCalledWith('/sw.js')
    await expect(register.mock.results[0].value).rejects.toThrow('insecure origin')
  })

  it('does nothing in development, where a worker would fight hot reload', () => {
    vi.stubEnv('PROD', false)
    vi.stubGlobal('navigator', { serviceWorker: { register: vi.fn() } })

    expect(installedLoadListener()).toBeNull()
  })

  it('does nothing where the browser has no service workers', () => {
    vi.stubEnv('PROD', true)
    vi.stubGlobal('navigator', {})

    expect(installedLoadListener()).toBeNull()
  })
})

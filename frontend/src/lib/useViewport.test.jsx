import { describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import { ThemeProvider } from '@mui/material/styles'
import { useBreakpointUp, useWide } from './useViewport'
import { mockViewport } from '../test/setup'
import { theme } from '../theme'

const wrapper = ({ children }) => <ThemeProvider theme={theme}>{children}</ThemeProvider>

describe('useViewport', () => {
  it('reads the theme breakpoints on a desktop', () => {
    expect(renderHook(() => useWide(), { wrapper }).result.current).toBe(true)
    expect(renderHook(() => useBreakpointUp('lg'), { wrapper }).result.current).toBe(true)
  })

  it('is narrow on a phone', () => {
    mockViewport({ matches: false })
    expect(renderHook(() => useWide(), { wrapper }).result.current).toBe(false)
  })

  it('asks for the breakpoint in pixels', () => {
    const queries = []
    mockViewport({
      matches: (query) => {
        queries.push(query)
        return true
      },
    })
    renderHook(() => useBreakpointUp('md'), { wrapper })
    expect(queries.some((query) => query.includes('900px'))).toBe(true)
  })
})

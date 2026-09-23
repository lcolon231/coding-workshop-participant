import { useTheme } from '@mui/material/styles'
import { useMediaQuery } from 'react-responsive'

/**
 * Whether the viewport is at least the given theme breakpoint wide.
 *
 * One place for the layout switch every screen makes (a table above `md`,
 * stacked rows below it), backed by React Responsive so the breakpoints
 * the theme declares are the ones the queries use.
 */
export function useBreakpointUp(key = 'md') {
  const theme = useTheme()
  return useMediaQuery({ minWidth: theme.breakpoints.values[key] })
}

/** The one switch most screens make: table and columns above `md`, stacked below. */
export function useWide() {
  return useBreakpointUp('md')
}

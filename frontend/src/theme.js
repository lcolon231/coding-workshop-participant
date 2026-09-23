import { createTheme } from '@mui/material/styles'

// One neutral base, one accent, one corner radius. Light and dark are
// generated as CSS variables and follow the system preference.
const RADIUS = 8

export const theme = createTheme({
  cssVariables: true,
  colorSchemes: {
    light: {
      palette: {
        primary: { main: '#1f5fb4', contrastText: '#ffffff' },
        // Status semantics only, kept as quiet as the neutrals around them.
        success: { main: '#2e7d4f' },
        warning: { main: '#9a5b14' },
        error: { main: '#b3372f' },
        background: { default: '#f7f7f8', paper: '#ffffff' },
        text: { primary: '#18181b', secondary: '#52525b' },
        divider: '#e4e4e7',
      },
    },
    dark: {
      palette: {
        primary: { main: '#8fb5ee', contrastText: '#0b1220' },
        success: { main: '#7fc79a' },
        warning: { main: '#e0a96a' },
        error: { main: '#f0958f' },
        background: { default: '#101114', paper: '#18191d' },
        text: { primary: '#f4f4f5', secondary: '#a1a1aa' },
        divider: '#2a2b31',
      },
    },
  },
  shape: { borderRadius: RADIUS },
  typography: {
    fontFamily: "'Geist Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
    h1: { fontSize: '1.75rem', fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.2 },
    body1: { fontSize: '1rem', lineHeight: 1.6 },
    body2: { fontSize: '0.875rem', lineHeight: 1.5 },
    button: { textTransform: 'none', fontWeight: 600, fontSize: '0.9375rem' },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          minHeight: 44,
          transition: 'transform 120ms ease, background-color 120ms ease',
          '&:active': { transform: 'scale(0.98)' },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: 'var(--mui-palette-background-paper)',
          // A textarea pads itself; padding the frame too would double it.
          '&.MuiInputBase-multiline': { padding: 0 },
        },
        input: { padding: '12px 14px' },
      },
    },
    MuiFormHelperText: {
      styleOverrides: { root: { marginLeft: 0, marginRight: 0, fontSize: '0.8125rem' } },
    },
    MuiAlert: {
      styleOverrides: { root: { borderRadius: RADIUS } },
    },
    MuiChip: {
      styleOverrides: { root: { borderRadius: RADIUS } },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: 'var(--mui-palette-divider)' },
        head: { fontWeight: 600, color: 'var(--mui-palette-text-secondary)' },
      },
    },
    MuiDialog: {
      styleOverrides: { paper: { borderRadius: RADIUS } },
    },
  },
})

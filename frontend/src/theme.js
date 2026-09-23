import { createTheme } from '@mui/material/styles'

// One neutral base tinted towards the accent, one purple accent, one corner
// radius. Light and dark are generated as CSS variables and follow the system
// preference.
const RADIUS = 8

// Chart colours, kept apart from the status semantics above. The eight
// categorical slots are used in this fixed order (see lib/charts.js); the
// brand purple leads, and adjacent pairs stay apart under colour-vision
// deficiency on both surfaces. One hue, `sequential`, carries plain
// magnitude. The dark values are the same hues re-stepped for the dark
// surface, not an automatic flip.
const CHART_LIGHT = {
  series: {
    violet: '#6d28d9',
    orange: '#eb6834',
    aqua: '#1baf7a',
    yellow: '#eda100',
    magenta: '#e87ba4',
    green: '#008300',
    blue: '#2a78d6',
    red: '#e34948',
  },
  sequential: '#6d28d9',
  track: '#e7e3f0',
}
const CHART_DARK = {
  series: {
    violet: '#b69cff',
    orange: '#d95926',
    aqua: '#199e70',
    yellow: '#c98500',
    magenta: '#d55181',
    green: '#008300',
    blue: '#3987e5',
    red: '#e66767',
  },
  sequential: '#b69cff',
  track: '#2c2838',
}

// A tint of the accent at a given alpha. `mainChannel` is the CSS-variable
// form MUI generates for each palette colour, so the tint follows the scheme.
const accent = (alpha) => `rgba(var(--mui-palette-primary-mainChannel) / ${alpha})`

// Soft, accent-tinted shadows in place of MUI's grey stack: cards and tiles
// use 1, menus 8, dialogs 24. Everything else keeps the default.
const base = createTheme()
const shadows = [...base.shadows]
shadows[1] = `0 1px 2px ${accent(0.06)}, 0 8px 24px -16px ${accent(0.35)}`
shadows[8] = `0 4px 12px ${accent(0.08)}, 0 16px 40px -16px ${accent(0.4)}`
shadows[24] = `0 8px 24px ${accent(0.1)}, 0 32px 64px -24px ${accent(0.5)}`

export const theme = createTheme({
  // A data attribute on <html> selects the scheme, so the toggle can override
  // the system preference; index.html sets it before first paint.
  cssVariables: { colorSchemeSelector: 'data' },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: '#6d28d9', light: '#8b5cf6', dark: '#5b21b6', contrastText: '#ffffff' },
        // Status semantics only, kept as quiet as the neutrals around them.
        success: { main: '#2e7d4f' },
        warning: { main: '#9a5b14' },
        error: { main: '#b3372f' },
        background: { default: '#f7f6fb', paper: '#ffffff' },
        text: { primary: '#18161f', secondary: '#56526a' },
        divider: '#e7e3f0',
        chart: CHART_LIGHT,
      },
    },
    dark: {
      palette: {
        primary: { main: '#b69cff', light: '#cdbbff', dark: '#9d7dff', contrastText: '#1a0b3d' },
        success: { main: '#7fc79a' },
        warning: { main: '#e0a96a' },
        error: { main: '#f0958f' },
        background: { default: '#110f18', paper: '#19161f' },
        text: { primary: '#f5f3fa', secondary: '#a7a2b8' },
        divider: '#2c2838',
        chart: CHART_DARK,
      },
    },
  },
  shape: { borderRadius: RADIUS },
  shadows,
  typography: {
    fontFamily: "'Geist Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
    h1: { fontSize: '1.75rem', fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.2 },
    body1: { fontSize: '1rem', lineHeight: 1.6 },
    body2: { fontSize: '0.875rem', lineHeight: 1.5 },
    button: { textTransform: 'none', fontWeight: 600, fontSize: '0.9375rem' },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // Keyboard focus matches the accent everywhere, links included.
        ':focus-visible': {
          outline: '2px solid var(--mui-palette-primary-main)',
          outlineOffset: 2,
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          minHeight: 44,
          transition: 'transform 120ms ease, background-color 120ms ease, box-shadow 120ms ease',
          '&:hover': { transform: 'translateY(-1px)' },
          '&:active': { transform: 'scale(0.98)' },
        },
        contained: {
          '&:hover': { boxShadow: `0 6px 16px -6px ${accent(0.6)}` },
          '&:active': { boxShadow: 'none' },
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
    MuiTableRow: {
      styleOverrides: {
        root: {
          transition: 'background-color 120ms ease',
          'tbody > &:hover': { backgroundColor: accent(0.05) },
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          '&:hover': { backgroundColor: accent(0.07) },
          '&.Mui-selected, &.Mui-selected:hover': { backgroundColor: accent(0.12) },
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: { border: '1px solid var(--mui-palette-divider)', backgroundImage: 'none' },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: RADIUS, border: '1px solid var(--mui-palette-divider)', backgroundImage: 'none' },
      },
    },
  },
})

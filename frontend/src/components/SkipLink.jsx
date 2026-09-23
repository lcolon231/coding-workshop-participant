import Link from '@mui/material/Link'

/**
 * "Skip to content": the first thing the keyboard reaches on every page.
 *
 * Invisible until focused, so sighted mouse users never see it, and a
 * keyboard user can jump past the bar's links and the report button without
 * tabbing through them on every page. The target is the `main` landmark,
 * which carries `id="main"` and `tabIndex={-1}` so it can take focus.
 */
export default function SkipLink() {
  return (
    <Link
      href="#main"
      sx={{
        position: 'absolute',
        left: 16,
        top: -100,
        zIndex: (theme) => theme.zIndex.appBar + 1,
        px: 2,
        py: 1,
        borderRadius: 1,
        bgcolor: 'primary.main',
        color: 'primary.contrastText',
        fontWeight: 600,
        textDecoration: 'none',
        '&:focus-visible': { top: 12 },
      }}
    >
      Skip to content
    </Link>
  )
}

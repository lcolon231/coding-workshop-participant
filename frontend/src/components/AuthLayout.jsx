import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'

// TODO: replace with real ACME facility photography, portrait, about 1200x1600.
const PANEL_IMAGE = 'https://picsum.photos/seed/acme-facility-lobby/1200/1600'

function Wordmark({ sx }) {
  return (
    <Typography component="p" sx={{ fontWeight: 600, letterSpacing: '-0.01em', ...sx }}>
      ACME Facility Incidents
    </Typography>
  )
}

/**
 * Two columns on desktop (photo panel, form), one column on phones.
 * The photo panel is decorative and hidden from assistive technology.
 */
export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <Box
      component="main"
      sx={{
        minHeight: '100dvh',
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '5fr 7fr' },
        bgcolor: 'background.default',
      }}
    >
      <Box
        component="aside"
        aria-hidden="true"
        sx={{
          display: { xs: 'none', md: 'block' },
          position: 'relative',
          overflow: 'hidden',
          // Seen until the photo arrives, and if it never does.
          background: 'linear-gradient(160deg, #2e1065 0%, #5b21b6 60%, #7c3aed 100%)',
        }}
      >
        <Box
          component="img"
          src={PANEL_IMAGE}
          alt=""
          sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
        />
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            // A purple wash over the photo so the panel reads as the brand,
            // darker at both ends where the text sits.
            background:
              'linear-gradient(180deg, rgba(46,16,101,0.72) 0%, rgba(76,29,149,0.35) 45%, rgba(30,10,70,0.78) 100%)',
          }}
        />
        <Wordmark sx={{ position: 'absolute', top: 32, left: 32, color: '#f4f4f5' }} />
        <Typography
          sx={{
            position: 'absolute',
            left: 32,
            right: 32,
            bottom: 32,
            maxWidth: '34ch',
            fontSize: '1.125rem',
            color: '#f4f4f5',
          }}
        >
          Report a facility issue, follow it to resolution, and see who is working on it.
        </Typography>
      </Box>

      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          px: { xs: 2, sm: 4 },
          py: { xs: 4, md: 8 },
          // A faint accent glow behind the form's top edge.
          backgroundImage:
            'radial-gradient(70% 280px at 50% -60px, rgba(var(--mui-palette-primary-mainChannel) / 0.12), transparent)',
          backgroundRepeat: 'no-repeat',
        }}
      >
        <Wordmark sx={{ display: { md: 'none' }, mb: 6 }} />
        <Box sx={{ width: '100%', maxWidth: 440, mx: 'auto', my: 'auto' }}>
          <Typography component="h1" variant="h1" sx={{ mb: 1 }}>
            {title}
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 4 }}>
            {subtitle}
          </Typography>
          {children}
          {footer && (
            <Typography color="text.secondary" sx={{ mt: 4 }}>
              {footer}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  )
}

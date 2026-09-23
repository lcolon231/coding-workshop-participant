import { Link as RouterLink } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { ShieldCheck, User, Wrench } from '@phosphor-icons/react'
import { PriorityChip, StatusChip } from '../components/IncidentChips'
import SkipLink from '../components/SkipLink'
import { usePageTitle } from '../lib/usePageTitle'

// TODO: replace with real ACME facility photography, landscape, about 1600x1000.
// The same placeholder seed as the sign-in panel, so the two screens match.
const HERO_IMAGE = 'https://picsum.photos/seed/acme-facility-lobby/1600/1000'

const STEPS = [
  {
    title: 'Report it',
    body: 'Pick the building, floor and seat, choose a category, and say what is wrong. Set how urgent it feels to you.',
  },
  {
    title: 'Facilities triages it',
    body: 'A Facility Admin is notified the moment you file. They confirm the priority and assign an engineer, who is notified straight away.',
  },
  {
    title: 'You confirm the fix',
    body: 'The engineer resolves it with a note on what was done. You close it, or reopen it if the problem is still there.',
  },
]

const ROLES = [
  {
    Icon: User,
    title: 'Employees',
    points: [
      'Report an issue with the exact place it happened',
      'Follow every step and add notes as it progresses',
      'Ask for it to be escalated if it gets worse',
    ],
  },
  {
    Icon: Wrench,
    title: 'Engineers',
    points: [
      'Get notified the moment work is assigned to you',
      'Start, block and resolve with a note for the record',
      'Keep internal notes that only staff can read',
    ],
  },
  {
    Icon: ShieldCheck,
    title: 'Facility Admins',
    points: [
      'Hear about every new report and assign the right engineer',
      'See every building and engineer at a glance',
      'Track response times against targets, and export a CSV',
    ],
  },
]

// Mirrors SLA_TARGETS in acme_core/reporting.py (D8). Stated here so the
// page needs no request; the reports page reads the live values.
const TARGETS = [
  { priority: 'Critical', target: '4 hours', color: 'error.main' },
  { priority: 'High', target: '24 hours', color: 'warning.main' },
  { priority: 'Medium', target: '3 days', color: 'text.secondary' },
  { priority: 'Low', target: '7 days', color: 'text.secondary' },
]

const HEADING = { fontSize: { xs: '1.75rem', md: '2.25rem' }, fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.15 }

function Actions({ inverted = false, full = false }) {
  const width = full ? { xs: '100%', sm: 'auto' } : 'auto'
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
      <Button
        component={RouterLink}
        to="/register"
        variant="contained"
        size="large"
        sx={{
          minHeight: 48,
          px: 2.75,
          width,
          ...(inverted && {
            bgcolor: 'background.paper',
            color: 'text.primary',
            '&:hover': { bgcolor: 'background.paper' },
          }),
        }}
      >
        Create an account
      </Button>
      <Button
        component={RouterLink}
        to="/login"
        variant="outlined"
        size="large"
        color="inherit"
        sx={{ minHeight: 48, px: 2.75, width, borderColor: inverted ? 'rgba(255,255,255,0.35)' : 'divider' }}
      >
        Sign in
      </Button>
    </Stack>
  )
}

/** The product, not a description of it: one incident card as the app draws it. */
function IncidentPreview() {
  const events = [
    { text: 'Assigned to Hank Vance', when: '2 hours ago', active: true },
    { text: 'Priority raised to High', when: '3 hours ago', active: true },
    { text: 'Reported by Eve Employee', when: 'yesterday', active: false },
  ]
  return (
    <Box aria-hidden="true" sx={{ position: 'relative', height: { xs: 380, md: 480 } }}>
      <Box
        component="img"
        src={HERO_IMAGE}
        alt=""
        sx={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: { xs: '100%', md: 560 },
          height: { xs: 220, md: 400 },
          objectFit: 'cover',
          borderRadius: 3,
          bgcolor: 'divider',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          left: { xs: 16, md: 0 },
          right: { xs: 16, md: 'auto' },
          bottom: 0,
          width: { md: 400 },
          p: { xs: 2, md: 2.75 },
          bgcolor: 'background.paper',
          border: 1,
          borderColor: 'divider',
          borderRadius: 3,
          boxShadow: 24,
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
        }}
      >
        <Box>
          <Typography sx={{ fontWeight: 600, color: 'primary.dark' }}>Aircon dripping on desk 3-14</Typography>
          <Typography variant="body2" color="text.secondary">
            Headquarters, floor 3, seat 3-14
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <StatusChip status="In Progress" />
          <PriorityChip priority="High" />
        </Stack>
        <Stack spacing={1} sx={{ pt: 1, borderTop: 1, borderColor: 'divider' }}>
          {events.map((event) => (
            <Stack key={event.text} direction="row" alignItems="center" spacing={1.25}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  bgcolor: event.active ? 'primary.main' : 'divider',
                }}
              />
              <Typography variant="body2">{event.text}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto' }}>
                {event.when}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Box>
    </Box>
  )
}

function Card({ children, tinted = false }) {
  return (
    <Box
      sx={{
        p: { xs: 2.75, md: 3.5 },
        border: 1,
        borderColor: 'divider',
        borderRadius: 3,
        bgcolor: tinted ? 'background.default' : 'background.paper',
        boxShadow: tinted ? 'none' : 1,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {children}
    </Box>
  )
}

function Bullet({ children }) {
  return (
    <Stack component="li" direction="row" spacing={1.25} sx={{ color: 'text.secondary' }}>
      <Box sx={{ flexShrink: 0, width: 6, height: 6, mt: '9px', borderRadius: '50%', bgcolor: 'primary.main' }} />
      <Typography variant="body2" sx={{ fontSize: '0.9375rem' }}>
        {children}
      </Typography>
    </Stack>
  )
}

/**
 * What an anonymous visitor sees at `/`: what the tool is, how an incident
 * moves, who it serves, and the response targets, with sign-in and
 * registration as the only two actions.
 *
 * Every claim on it is something the app does today; the targets mirror the
 * constants the reports are measured against.
 */
export default function LandingPage() {
  usePageTitle()
  return (
    <Box sx={{ minHeight: '100dvh', bgcolor: 'background.default', color: 'text.primary' }}>
      <SkipLink />
      <Box component="header" sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}>
        <Container
          maxWidth="lg"
          sx={{ minHeight: { xs: 60, md: 72 }, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}
        >
          <Stack direction="row" alignItems="center" spacing={5}>
            <Typography sx={{ fontWeight: 600, letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>
              ACME Facility Incidents
            </Typography>
            <Box component="nav" aria-label="Page" sx={{ display: { xs: 'none', md: 'flex' }, gap: 0.5 }}>
              {[
                ['#how', 'How it works'],
                ['#roles', 'For your team'],
                ['#targets', 'Response targets'],
              ].map(([href, label]) => (
                <Button key={href} href={href} color="inherit" size="small" sx={{ color: 'text.secondary', px: 1.5 }}>
                  {label}
                </Button>
              ))}
            </Box>
          </Stack>
          <Stack direction="row" spacing={1.25}>
            <Button component={RouterLink} to="/login" variant="outlined" color="inherit" sx={{ minHeight: 40, borderColor: 'divider' }}>
              Sign in
            </Button>
            <Button component={RouterLink} to="/register" variant="contained" sx={{ minHeight: 40, display: { xs: 'none', sm: 'inline-flex' } }}>
              Create an account
            </Button>
          </Stack>
        </Container>
      </Box>

      <Box component="main" id="main" tabIndex={-1} sx={{ outline: 'none' }}>
      <Container maxWidth="lg" sx={{ py: { xs: 5, md: 12 } }}>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
            gap: { xs: 4, md: 8 },
            alignItems: 'center',
          }}
        >
          <Stack spacing={3} sx={{ maxWidth: 540 }}>
            <Typography
              component="p"
              sx={{
                alignSelf: 'flex-start',
                px: 1.5,
                py: 0.75,
                borderRadius: 999,
                bgcolor: 'rgba(var(--mui-palette-primary-mainChannel) / 0.1)',
                color: 'primary.dark',
                fontSize: '0.8125rem',
                fontWeight: 600,
                letterSpacing: '0.02em',
                textTransform: 'uppercase',
              }}
            >
              Internal facilities tool
            </Typography>
            <Typography
              component="h1"
              sx={{ fontSize: { xs: '2.25rem', md: '3.5rem' }, fontWeight: 600, letterSpacing: '-0.025em', lineHeight: 1.08 }}
            >
              Something broken at work? Report it in a minute.
            </Typography>
            <Typography sx={{ fontSize: { xs: '1.0625rem', md: '1.25rem' }, color: 'text.secondary' }}>
              Tell facilities what is wrong and where. Then follow the incident from report to fix, and see who is working on it.
            </Typography>
            <Actions full />
            <Typography variant="body2" color="text.secondary">
              Any @acme.inc address can register. Engineer and admin accounts are set up by a Facility Admin.
            </Typography>
          </Stack>
          <IncidentPreview />
        </Box>
      </Container>

      <Box component="section" id="how" sx={{ bgcolor: 'background.paper', borderTop: 1, borderBottom: 1, borderColor: 'divider', py: { xs: 6, md: 11 } }}>
        <Container maxWidth="lg">
          <Stack spacing={{ xs: 3, md: 6 }}>
            <Stack spacing={1.5} sx={{ maxWidth: 640 }}>
              <Typography component="h2" sx={HEADING}>
                From report to fix, in three steps
              </Typography>
              <Typography color="text.secondary" sx={{ fontSize: '1.0625rem' }}>
                Every incident moves through the same path, and everyone involved can see where it is.
              </Typography>
            </Stack>
            <Box component="ol" sx={{ m: 0, p: 0, listStyle: 'none', display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: { xs: 1.75, md: 4 } }}>
              {STEPS.map((step, index) => (
                <Box component="li" key={step.title}>
                  <Card tinted>
                    <Stack direction={{ xs: 'row', md: 'column' }} spacing={2} alignItems={{ xs: 'flex-start', md: 'stretch' }}>
                      <Box
                        sx={{
                          flexShrink: 0,
                          width: 40,
                          height: 40,
                          borderRadius: '50%',
                          bgcolor: 'primary.main',
                          color: 'primary.contrastText',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 600,
                        }}
                      >
                        {index + 1}
                      </Box>
                      <Stack spacing={1}>
                        <Typography component="h3" sx={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.01em' }}>
                          {step.title}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.9375rem' }}>
                          {step.body}
                        </Typography>
                      </Stack>
                    </Stack>
                  </Card>
                </Box>
              ))}
            </Box>
          </Stack>
        </Container>
      </Box>

      <Box component="section" id="roles" sx={{ py: { xs: 6, md: 11 } }}>
        <Container maxWidth="lg">
          <Stack spacing={{ xs: 3, md: 6 }}>
            <Stack spacing={1.5} sx={{ maxWidth: 640 }}>
              <Typography component="h2" sx={HEADING}>
                Built for everyone in the building
              </Typography>
              <Typography color="text.secondary" sx={{ fontSize: '1.0625rem' }}>
                One tool, three views. Each person sees what concerns them and nothing else.
              </Typography>
            </Stack>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: { xs: 1.75, md: 4 } }}>
              {ROLES.map(({ Icon, title, points }) => (
                <Card key={title}>
                  <Stack direction={{ xs: 'row', md: 'column' }} spacing={{ xs: 1.5, md: 2 }} alignItems={{ xs: 'center', md: 'flex-start' }}>
                    <Box sx={{ color: 'primary.main', display: 'inline-flex' }}>
                      <Icon size={28} aria-hidden="true" />
                    </Box>
                    <Typography component="h3" sx={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.01em' }}>
                      {title}
                    </Typography>
                  </Stack>
                  <Stack component="ul" spacing={1.25} sx={{ m: 0, p: 0, listStyle: 'none' }}>
                    {points.map((point) => (
                      <Bullet key={point}>{point}</Bullet>
                    ))}
                  </Stack>
                </Card>
              ))}
            </Box>
          </Stack>
        </Container>
      </Box>

      <Box component="section" id="targets" sx={{ pb: { xs: 6, md: 11 } }}>
        <Container maxWidth="lg">
          <Box
            sx={{
              p: { xs: 3, md: 5.5 },
              border: 1,
              borderColor: 'divider',
              borderRadius: 3,
              bgcolor: 'background.paper',
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
              gap: { xs: 2.5, md: 6 },
              alignItems: 'center',
            }}
          >
            <Stack spacing={1.5}>
              <Typography component="h2" sx={{ ...HEADING, fontSize: { xs: '1.5rem', md: '1.75rem' } }}>
                Response targets you can hold us to
              </Typography>
              <Typography color="text.secondary">
                Target time from report to resolution, by priority. Facility Admins see how every building and engineer measures against them.
              </Typography>
            </Stack>
            <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1.5 }}>
              {TARGETS.map((row) => (
                <Box key={row.priority} sx={{ p: 2, borderRadius: 2, bgcolor: 'background.default', border: 1, borderColor: 'divider' }}>
                  <Typography component="dt" variant="body2" sx={{ fontWeight: 600, color: row.color }}>
                    {row.priority}
                  </Typography>
                  <Typography component="dd" sx={{ m: 0, fontSize: '1.5rem', fontWeight: 600, letterSpacing: '-0.02em' }}>
                    {row.target}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        </Container>
      </Box>

      <Box component="section" sx={{ bgcolor: 'text.primary', color: 'background.paper', py: { xs: 6, md: 10 } }}>
        <Container
          maxWidth="lg"
          sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { md: 'center' }, justifyContent: 'space-between', gap: { xs: 3, md: 6 } }}
        >
          <Stack spacing={1.25} sx={{ maxWidth: 640 }}>
            <Typography component="h2" sx={HEADING}>
              Ready when you are.
            </Typography>
            <Typography sx={{ fontSize: '1.0625rem', opacity: 0.75 }}>
              Sign in with your ACME account, or create one with your @acme.inc email. Install it from your browser menu and it stays on your home screen.
            </Typography>
          </Stack>
          <Box sx={{ flexShrink: 0 }}>
            <Actions inverted full />
          </Box>
        </Container>
      </Box>

      </Box>

      <Container
        component="footer"
        maxWidth="lg"
        sx={{ py: 3.5, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, justifyContent: 'space-between', gap: 0.75, color: 'text.secondary', fontSize: '0.875rem' }}
      >
        <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.primary' }}>
          ACME Facility Incidents
        </Typography>
        <Typography variant="body2">An internal tool for ACME staff. Not accessible outside the company.</Typography>
      </Container>
    </Box>
  )
}

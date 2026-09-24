import { useState } from 'react'
import { Link as RouterLink, NavLink, Outlet } from 'react-router-dom'
import AppBar from '@mui/material/AppBar'
import Avatar from '@mui/material/Avatar'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { Plus, SignOut } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthContext'
import { initials } from '../lib/format'
import NotificationBell from './NotificationBell'
import SkipLink from './SkipLink'
import ThemeToggle from './ThemeToggle'

const ADMIN = ['Facility Admin']

/** Links without `roles` show for everyone; the rest only for the roles listed. */
const NAV = [
  { to: '/', label: 'Incidents', end: true },
  { to: '/escalations', label: 'Escalations', roles: ADMIN },
  { to: '/users', label: 'Users', roles: ADMIN },
  { to: '/facilities', label: 'Facilities', roles: ADMIN },
  { to: '/reports', label: 'Reports', roles: ADMIN },
]

function UserMenu({ user, onSignOut }) {
  const [anchor, setAnchor] = useState(null)
  const open = Boolean(anchor)
  return (
    <>
      <IconButton
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? 'account-menu' : undefined}
        onClick={(event) => setAnchor(event.currentTarget)}
        sx={{ p: 0.5 }}
      >
        <Avatar
          sx={{
            width: 34,
            height: 34,
            fontSize: '0.8125rem',
            fontWeight: 600,
            bgcolor: 'primary.main',
            background: 'linear-gradient(135deg, var(--mui-palette-primary-dark), var(--mui-palette-primary-light))',
            color: 'primary.contrastText',
          }}
        >
          {initials(user.full_name)}
        </Avatar>
      </IconButton>
      <Menu
        id="account-menu"
        anchorEl={anchor}
        open={open}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { minWidth: 220, mt: 1 } } }}
      >
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography sx={{ fontWeight: 600, lineHeight: 1.3 }}>{user.full_name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {user.role}
          </Typography>
        </Box>
        <Divider />
        <MenuItem
          onClick={() => {
            setAnchor(null)
            onSignOut()
          }}
        >
          <ListItemIcon>
            <SignOut size={18} />
          </ListItemIcon>
          Sign out
        </MenuItem>
      </Menu>
    </>
  )
}

/**
 * The signed-in frame: one 64px bar with the wordmark, the primary links,
 * the report action, the notification bell (admins hear about reports,
 * engineers about assignments, reporters about outcomes) and the account
 * menu, over a contained page.
 *
 * The bar never wraps: on phones the report action becomes an icon button,
 * the wordmark shortens, and an admin's five links scroll sideways rather
 * than squeezing.
 */
export default function AppShell() {
  const { user, signOut } = useAuth()
  const links = NAV.filter((item) => !item.roles || item.roles.includes(user.role))

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.default',
        // A faint accent glow behind the top of every page.
        backgroundImage:
          'radial-gradient(80% 320px at 50% -80px, rgba(var(--mui-palette-primary-mainChannel) / 0.09), transparent)',
        backgroundRepeat: 'no-repeat',
      }}
    >
      <SkipLink />
      <AppBar
        position="sticky"
        elevation={0}
        color="transparent"
        sx={{
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
          // A hairline of the accent along the top edge.
          '&::before': {
            content: '""',
            position: 'absolute',
            inset: '0 0 auto 0',
            height: 3,
            background: 'linear-gradient(90deg, var(--mui-palette-primary-dark), var(--mui-palette-primary-light))',
          },
        }}
      >
        <Toolbar
          disableGutters
          sx={{
            minHeight: { xs: 60, md: 64 },
            width: '100%',
            maxWidth: 1200,
            mx: 'auto',
            px: { xs: 2, sm: 3 },
            gap: { xs: 1, sm: 2 },
          }}
        >
          <Typography
            component={RouterLink}
            to="/"
            sx={{
              fontWeight: 600,
              letterSpacing: '-0.01em',
              color: 'text.primary',
              textDecoration: 'none',
              whiteSpace: 'nowrap',
              mr: { xs: 0, sm: 2 },
              display: 'inline-flex',
              alignItems: 'center',
              gap: 1,
            }}
          >
            <Box
              component="span"
              aria-hidden="true"
              sx={{
                width: 12,
                height: 12,
                borderRadius: '4px',
                background: 'linear-gradient(135deg, var(--mui-palette-primary-dark), var(--mui-palette-primary-light))',
                flexShrink: 0,
              }}
            />
            <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
              ACME Facility Incidents
            </Box>
            <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>
              ACME
            </Box>
          </Typography>

          <Box
            component="nav"
            aria-label="Primary"
            sx={{
              display: 'flex',
              gap: 0.5,
              flex: 1,
              minWidth: 0,
              overflowX: 'auto',
              scrollbarWidth: 'none',
              '&::-webkit-scrollbar': { display: 'none' },
            }}
          >
            {links.map((item) => (
              <Button
                key={item.to}
                component={NavLink}
                to={item.to}
                end={item.end}
                color="inherit"
                size="small"
                sx={{
                  minHeight: 36,
                  px: 1.5,
                  flexShrink: 0,
                  color: 'text.secondary',
                  '&:hover': { transform: 'none', bgcolor: 'rgba(var(--mui-palette-primary-mainChannel) / 0.06)' },
                  '&.active': {
                    color: 'primary.main',
                    bgcolor: 'rgba(var(--mui-palette-primary-mainChannel) / 0.1)',
                  },
                }}
              >
                {item.label}
              </Button>
            ))}
          </Box>

          <Button
            component={RouterLink}
            to="/incidents/new"
            variant="contained"
            size="small"
            startIcon={<Plus size={16} weight="bold" />}
            sx={{ minHeight: 36, whiteSpace: 'nowrap', display: { xs: 'none', sm: 'inline-flex' } }}
          >
            Report an incident
          </Button>
          <IconButton
            component={RouterLink}
            to="/incidents/new"
            aria-label="Report an incident"
            color="primary"
            sx={{ display: { xs: 'inline-flex', sm: 'none' } }}
          >
            <Plus size={22} weight="bold" />
          </IconButton>

          <ThemeToggle />
          <NotificationBell />
          <UserMenu user={user} onSignOut={signOut} />
        </Toolbar>
      </AppBar>

      <Container
        component="main"
        id="main"
        tabIndex={-1}
        maxWidth="lg"
        sx={{ flex: 1, py: { xs: 3, md: 5 }, outline: 'none' }}
      >
        <Outlet />
      </Container>
    </Box>
  )
}

import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useAuth } from './auth/AuthContext'
import AppShell from './components/AppShell'
import IncidentPage from './pages/IncidentPage'
import IncidentsPage from './pages/IncidentsPage'
import LoginPage from './pages/LoginPage'
import NewIncidentPage from './pages/NewIncidentPage'
import RegisterPage from './pages/RegisterPage'

/**
 * Gate everything behind a loaded user.
 *
 * No session sends the visitor to sign in, remembering where they were going.
 * A session still being checked shows the frame of the page rather than a
 * flash of the sign-in screen.
 */
function RequireUser({ children }) {
  const location = useLocation()
  const { status, error, retry, signOut } = useAuth()

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (status === 'error') {
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <Stack spacing={2} alignItems="flex-start" sx={{ maxWidth: 440 }} role="alert">
          <Typography component="h1" variant="h1">
            Could not load your account
          </Typography>
          <Typography color="text.secondary">{error}</Typography>
          <Stack direction="row" spacing={1.5}>
            <Button variant="contained" onClick={retry}>
              Try again
            </Button>
            <Button variant="outlined" onClick={signOut}>
              Sign out
            </Button>
          </Stack>
        </Stack>
      </Box>
    )
  }
  if (status === 'loading') {
    return (
      <Box aria-busy="true" aria-label="Loading your account" sx={{ minHeight: '100dvh' }}>
        <Skeleton variant="rectangular" height={64} />
        <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
          <Skeleton width={220} height={40} />
          <Skeleton height={28} sx={{ mt: 3 }} />
          <Skeleton height={28} />
          <Skeleton height={28} />
        </Box>
      </Box>
    )
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <RequireUser>
            <AppShell />
          </RequireUser>
        }
      >
        <Route index element={<IncidentsPage />} />
        <Route path="incidents" element={<Navigate to="/" replace />} />
        <Route path="incidents/new" element={<NewIncidentPage />} />
        <Route path="incidents/:incidentId" element={<IncidentPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

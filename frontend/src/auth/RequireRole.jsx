import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'

/**
 * Keep a route to the roles listed. Anyone else lands on the incident list.
 *
 * Sits inside `RequireUser`, so the user is already loaded; the API enforces
 * the same rule on every request, this only avoids showing a screen that
 * would answer 403 to everything.
 */
export default function RequireRole({ roles, children }) {
  const { user } = useAuth()
  if (!roles.includes(user?.role)) return <Navigate to="/" replace />
  return children
}

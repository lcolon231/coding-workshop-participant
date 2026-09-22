import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)

/** `{ status, user, error, signOut, retry }`. `status` is loading, signed-in, anonymous or error. */
export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

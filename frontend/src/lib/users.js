/**
 * Vocabulary for the user management screen.
 *
 * Role values are the API's display strings. An Engineer carries a specialty
 * and an Employee an occupation; a Facility Admin carries neither, and the
 * API rejects the wrong one for the role.
 */

export const ROLES = ['Employee', 'Engineer', 'Facility Admin']

/** The role-specific field the API requires for this role, if any. */
export function roleNeeds(role) {
  if (role === 'Engineer') return 'specialty'
  if (role === 'Employee') return 'occupation'
  return null
}

export const USER_SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Newest first' },
  { value: 'created_at:asc', label: 'Oldest first' },
  { value: 'full_name:asc', label: 'Name, A to Z' },
  { value: 'email:asc', label: 'Email, A to Z' },
  { value: 'role:asc', label: 'Role' },
]

/**
 * An engineer's load as a word rather than a fraction. Anyone at or over
 * their concurrent-incident limit is "High"; at half of it or more,
 * "Medium"; otherwise "Low". A limit of zero is always full.
 */
export function loadLevel(engineer) {
  const open = engineer.open_assignments ?? 0
  const limit = engineer.max_concurrent_incidents ?? 0
  if (open >= limit) return 'High'
  if (open * 2 >= limit) return 'Medium'
  return 'Low'
}

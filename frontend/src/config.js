/** Build-time configuration, read from `VITE_*` environment variables. */

/** The email domain self-registration accepts. The backend enforces it; this is for hints. */
export const SIGNUP_DOMAIN = import.meta.env.VITE_SIGNUP_DOMAIN || 'acme.inc'

/** Minimum password length, mirrored from `acme_core.security.passwords`. */
export const MIN_PASSWORD_LENGTH = 12

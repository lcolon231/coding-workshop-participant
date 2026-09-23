import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormHelperText from '@mui/material/FormHelperText'
import Stack from '@mui/material/Stack'
import Field from '../Field'
import PasswordField from '../PasswordField'
import SelectField from '../SelectField'
import { MIN_PASSWORD_LENGTH, SIGNUP_DOMAIN } from '../../config'
import { focusFirstError, splitDetails } from '../../lib/formErrors'
import { ROLES, roleNeeds } from '../../lib/users'
import { ApiError } from '../../services/api'

const FIELD_ORDER = ['full_name', 'email', 'password', 'role', 'specialty', 'occupation', 'date_of_birth', 'is_active']

function todayUtc() {
  return new Date().toISOString().slice(0, 10)
}

function startingValues(user) {
  return {
    full_name: user?.full_name ?? '',
    email: '',
    password: '',
    role: user?.role ?? 'Employee',
    specialty: '',
    occupation: user?.occupation ?? '',
    date_of_birth: user?.date_of_birth ?? '',
    is_active: user?.is_active ?? true,
  }
}

function validate(values, { editing }) {
  const errors = {}
  if (!values.full_name.trim()) errors.full_name = 'Enter their full name.'
  if (!editing) {
    const email = values.email.trim().toLowerCase()
    if (!email) errors.email = 'Enter their email address.'
    else if (email.split('@')[1] !== SIGNUP_DOMAIN) errors.email = `Use an @${SIGNUP_DOMAIN} address.`
    if (!values.password) errors.password = 'Choose a password.'
    else if (values.password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`
    }
  }
  const needs = roleNeeds(values.role)
  // On edit an Engineer may already have a profile, so the API decides.
  if (needs && !values[needs].trim() && !(editing && needs === 'specialty')) {
    errors[needs] = needs === 'specialty' ? 'Enter their specialty.' : 'Enter their occupation.'
  }
  if (!values.date_of_birth) errors.date_of_birth = 'Enter their date of birth.'
  else if (values.date_of_birth > todayUtc()) errors.date_of_birth = 'Date of birth cannot be in the future.'
  return errors
}

/**
 * Create a user, or edit one.
 *
 * Creating is the only place a role is chosen freely. Editing sends only
 * what changed, because `PUT` is partial, and never touches email or
 * password, which the API does not let an admin change. An admin editing
 * themselves cannot change their own role or deactivate themselves; the
 * API refuses both, so the controls are locked with a reason.
 */
export default function UserDialog({ open, user, self = false, onSubmit, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      {open && <UserForm user={user} self={self} onSubmit={onSubmit} onClose={onClose} />}
    </Dialog>
  )
}

/** Mounted fresh each time the dialog opens. */
function UserForm({ user, self, onSubmit, onClose }) {
  const editing = Boolean(user)
  const [values, setValues] = useState(() => startingValues(user))
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const needs = roleNeeds(values.role)

  function handleChange(event) {
    const { name, value, type, checked } = event.target
    setValues((current) => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
    setFieldErrors((current) => (current[name] ? { ...current, [name]: undefined } : current))
  }

  function buildBody() {
    if (!editing) {
      const body = {
        email: values.email.trim().toLowerCase(),
        password: values.password,
        full_name: values.full_name.trim(),
        role: values.role,
        date_of_birth: values.date_of_birth,
      }
      if (needs) body[needs] = values[needs].trim()
      return body
    }
    const body = {}
    if (values.full_name.trim() !== user.full_name) body.full_name = values.full_name.trim()
    if (values.role !== user.role) body.role = values.role
    if (values.date_of_birth !== (user.date_of_birth ?? '')) body.date_of_birth = values.date_of_birth
    if (values.is_active !== user.is_active) body.is_active = values.is_active
    if (needs === 'specialty' && values.specialty.trim()) body.specialty = values.specialty.trim()
    if (needs === 'occupation' && values.occupation.trim() !== (user.occupation ?? '')) {
      body.occupation = values.occupation.trim()
    }
    return body
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const clientErrors = validate(values, { editing })
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors)
      focusFirstError(clientErrors, FIELD_ORDER)
      return
    }
    const body = buildBody()
    if (editing && Object.keys(body).length === 0) {
      onClose()
      return
    }

    setSubmitting(true)
    setFormError(null)
    try {
      await onSubmit(body)
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const { fieldErrors: serverErrors, formErrors } = splitDetails(err.details, FIELD_ORDER)
        setFieldErrors(serverErrors)
        focusFirstError(serverErrors, FIELD_ORDER)
        const hasInline = Object.keys(serverErrors).length > 0
        setFormError(formErrors.length > 0 ? formErrors.join(' ') : hasInline ? null : err.message)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-busy={submitting}>
      <DialogTitle sx={{ fontWeight: 600 }}>{editing ? `Edit ${user.full_name}` : 'New user'}</DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ pt: 1 }}>
          {formError && <Alert severity="error">{formError}</Alert>}
          <Field
            id="full_name"
            label="Full name"
            autoComplete="off"
            autoFocus
            value={values.full_name}
            onChange={handleChange}
            error={fieldErrors.full_name}
          />
          {editing ? (
            <Field id="email" label="Email" value={user.email} disabled helperText="Cannot be changed." />
          ) : (
            <Field
              id="email"
              label="Work email"
              type="email"
              autoComplete="off"
              helperText={`An @${SIGNUP_DOMAIN} address.`}
              value={values.email}
              onChange={handleChange}
              error={fieldErrors.email}
            />
          )}
          {!editing && (
            <PasswordField
              id="password"
              label="Temporary password"
              autoComplete="new-password"
              helperText={`At least ${MIN_PASSWORD_LENGTH} characters. They can change it once signed in.`}
              value={values.password}
              onChange={handleChange}
              error={fieldErrors.password}
            />
          )}
          <SelectField
            id="role"
            label="Role"
            value={values.role}
            onChange={handleChange}
            error={fieldErrors.role}
            disabled={self}
            helperText={
              self
                ? 'You cannot change your own role.'
                : editing
                  ? 'Changing the role signs them out everywhere.'
                  : undefined
            }
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </SelectField>
          {needs === 'specialty' && (
            <Field
              id="specialty"
              label="Specialty"
              helperText={
                editing
                  ? 'Required unless they already have an engineer profile. Leave blank to keep it.'
                  : 'What they work on, e.g. HVAC or Workplace Technology.'
              }
              value={values.specialty}
              onChange={handleChange}
              error={fieldErrors.specialty}
              inputAttributes={{ maxLength: 100 }}
            />
          )}
          {needs === 'occupation' && (
            <Field
              id="occupation"
              label="Occupation"
              value={values.occupation}
              onChange={handleChange}
              error={fieldErrors.occupation}
              inputAttributes={{ maxLength: 100 }}
            />
          )}
          <Field
            id="date_of_birth"
            label="Date of birth"
            type="date"
            value={values.date_of_birth}
            onChange={handleChange}
            error={fieldErrors.date_of_birth}
            inputAttributes={{ max: todayUtc() }}
          />
          {editing && (
            <div>
              <FormControlLabel
                control={
                  <Checkbox
                    id="is_active"
                    name="is_active"
                    checked={values.is_active}
                    onChange={handleChange}
                    disabled={self}
                  />
                }
                label="Active"
              />
              <FormHelperText>
                {self
                  ? 'You cannot deactivate your own account.'
                  : 'An inactive user cannot sign in. Their incidents are kept.'}
              </FormHelperText>
            </div>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" variant="contained" disabled={submitting}>
          {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create user'}
        </Button>
      </DialogActions>
    </form>
  )
}

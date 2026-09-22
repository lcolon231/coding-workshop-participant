import { useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import AuthLayout from '../components/AuthLayout'
import Field from '../components/Field'
import PasswordField from '../components/PasswordField'
import { MIN_PASSWORD_LENGTH, SIGNUP_DOMAIN } from '../config'
import { focusFirstError, splitDetails } from '../lib/formErrors'
import { ApiError } from '../services/api'
import { register } from '../services/auth'

const FIELDS = ['full_name', 'email', 'password', 'occupation', 'date_of_birth']

/** Today as the API sees it: the UTC calendar date. */
function todayUtc() {
  return new Date().toISOString().slice(0, 10)
}

function validate(values) {
  const errors = {}
  if (!values.full_name.trim()) errors.full_name = 'Enter your full name.'

  const email = values.email.trim().toLowerCase()
  if (!email) errors.email = 'Enter your email address.'
  else if (email.split('@')[1] !== SIGNUP_DOMAIN) errors.email = `Use your @${SIGNUP_DOMAIN} address.`

  if (!values.password) errors.password = 'Choose a password.'
  else if (values.password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`
  }

  if (!values.occupation.trim()) errors.occupation = 'Enter your occupation.'

  if (!values.date_of_birth) errors.date_of_birth = 'Enter your date of birth.'
  else if (values.date_of_birth > todayUtc()) {
    errors.date_of_birth = 'Date of birth cannot be in the future.'
  }
  return errors
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const [values, setValues] = useState({
    full_name: '',
    email: '',
    password: '',
    occupation: '',
    date_of_birth: '',
  })
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => (current[name] ? { ...current, [name]: undefined } : current))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const clientErrors = validate(values)
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors)
      focusFirstError(clientErrors, FIELDS)
      return
    }

    setSubmitting(true)
    setFormError(null)
    try {
      const { message } = await register({
        full_name: values.full_name.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        occupation: values.occupation.trim(),
        date_of_birth: values.date_of_birth,
      })
      // The response is the same whether or not the address was new, so the
      // only sensible next step is the sign-in screen.
      navigate('/login', { replace: true, state: { notice: message } })
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const { fieldErrors: serverErrors, formErrors } = splitDetails(err.details, FIELDS)
        setFieldErrors(serverErrors)
        focusFirstError(serverErrors, FIELDS)
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
    <AuthLayout
      title="Create your account"
      subtitle={`Any @${SIGNUP_DOMAIN} address can register and report incidents.`}
      footer={
        <>
          Already have an account?{' '}
          <Link component={RouterLink} to="/login">
            Sign in
          </Link>
        </>
      }
    >
      <Stack component="form" noValidate onSubmit={handleSubmit} aria-busy={submitting} spacing={3}>
        {formError && <Alert severity="error">{formError}</Alert>}
        <Field
          id="full_name"
          label="Full name"
          autoComplete="name"
          autoFocus
          value={values.full_name}
          onChange={handleChange}
          error={fieldErrors.full_name}
        />
        <Field
          id="email"
          label="Work email"
          type="email"
          autoComplete="email"
          helperText={`Your @${SIGNUP_DOMAIN} address.`}
          value={values.email}
          onChange={handleChange}
          error={fieldErrors.email}
        />
        <PasswordField
          id="password"
          label="Password"
          autoComplete="new-password"
          helperText={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          value={values.password}
          onChange={handleChange}
          error={fieldErrors.password}
        />
        <Field
          id="occupation"
          label="Occupation"
          autoComplete="organization-title"
          helperText="Your job title, for example Financial Analyst."
          value={values.occupation}
          onChange={handleChange}
          error={fieldErrors.occupation}
        />
        <Field
          id="date_of_birth"
          label="Date of birth"
          type="date"
          autoComplete="bday"
          inputAttributes={{ max: todayUtc(), min: '1900-01-01' }}
          value={values.date_of_birth}
          onChange={handleChange}
          error={fieldErrors.date_of_birth}
        />
        <Button type="submit" variant="contained" size="large" fullWidth disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </Stack>
    </AuthLayout>
  )
}

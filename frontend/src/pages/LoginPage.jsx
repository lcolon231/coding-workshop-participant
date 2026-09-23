import { useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import AuthLayout from '../components/AuthLayout'
import Field from '../components/Field'
import PasswordField from '../components/PasswordField'
import { focusFirstError, splitDetails } from '../lib/formErrors'
import { ApiError } from '../services/api'
import { login } from '../services/auth'
import { saveSession } from '../services/session'

const FIELDS = ['email', 'password']

function validate(values) {
  const errors = {}
  if (!values.email.trim()) errors.email = 'Enter your email address.'
  if (!values.password) errors.password = 'Enter your password.'
  return errors
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const notice = location.state?.notice ?? null
  const [values, setValues] = useState({ email: '', password: '' })
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
      const tokens = await login({ email: values.email.trim(), password: values.password })
      saveSession(tokens)
      navigate(location.state?.from ?? '/', { replace: true })
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
      title="Sign in"
      subtitle="Use your ACME account to report and track facility incidents."
      footer={
        <>
          New here?{' '}
          <Link component={RouterLink} to="/register">
            Create an account
          </Link>
        </>
      }
    >
      <Stack component="form" noValidate onSubmit={handleSubmit} aria-busy={submitting} spacing={3}>
        {notice && <Alert severity="success">{notice}</Alert>}
        {formError && <Alert severity="error">{formError}</Alert>}
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          autoFocus
          value={values.email}
          onChange={handleChange}
          error={fieldErrors.email}
        />
        <PasswordField
          id="password"
          label="Password"
          autoComplete="current-password"
          value={values.password}
          onChange={handleChange}
          error={fieldErrors.password}
        />
        <Button type="submit" variant="contained" size="large" fullWidth disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </Stack>
    </AuthLayout>
  )
}

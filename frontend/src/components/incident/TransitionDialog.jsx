import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Field from '../Field'
import SelectField from '../SelectField'
import { focusFirstError, splitDetails } from '../../lib/formErrors'
import { ApiError } from '../../services/api'

const FIELD_ORDER = ['assignee_id', 'blocked_reason', 'resolution_note']

const COPY = {
  blocked_reason: {
    label: 'What is it waiting on',
    help: 'A part, a contractor, access to a room. The reporter will see this.',
  },
  resolution_note: {
    label: 'Resolution note',
    help: 'What was done. This is recorded in the history and shown to the reporter.',
  },
}

/**
 * Confirm one workflow move and collect exactly what the edge requires.
 *
 * `option` is one of the incident's `allowed_transitions`, so the API has
 * already said this caller may take it; the dialog only supplies the fields.
 * An engineer who must name an assignee names themselves; an admin picks from
 * the active engineers.
 */
export default function TransitionDialog({
  open,
  option,
  incident,
  user,
  engineers,
  onSubmit,
  onClose,
}) {
  if (!option) return null
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <TransitionForm
        option={option}
        incident={incident}
        user={user}
        engineers={engineers}
        onSubmit={onSubmit}
        onClose={onClose}
      />
    </Dialog>
  )
}

/** Mounted fresh each time the dialog opens, so nothing carries over between moves. */
function TransitionForm({ option, incident, user, engineers, onSubmit, onClose }) {
  const [values, setValues] = useState({})
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)


  const requires = option.requires ?? []
  const needsAssignee = requires.includes('assignee_id')
  const selfAssign = needsAssignee && user.role === 'Engineer'
  const adminAssign = needsAssignee && user.role === 'Facility Admin'
  const textFields = requires.filter((name) => COPY[name])

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => (current[name] ? { ...current, [name]: undefined } : current))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const errors = {}
    for (const name of textFields) {
      if (!values[name]?.trim()) errors[name] = 'This is required to continue.'
    }
    if (adminAssign && !values.assignee_id) errors.assignee_id = 'Choose an engineer.'
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      focusFirstError(errors, FIELD_ORDER)
      return
    }

    const body = { target_status: option.to }
    for (const name of textFields) body[name] = values[name].trim()
    if (selfAssign) body.assignee_id = user.id
    if (adminAssign) body.assignee_id = values.assignee_id

    setSubmitting(true)
    setFormError(null)
    try {
      await onSubmit(body)
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const { fieldErrors: serverErrors, formErrors } = splitDetails(err.details, FIELD_ORDER)
        setFieldErrors(serverErrors)
        focusFirstError(serverErrors, FIELD_ORDER)
        setFormError(formErrors.length > 0 ? formErrors.join(' ') : null)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-busy={submitting}>
      <DialogTitle sx={{ fontWeight: 600 }}>{option.label}</DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ pt: 1 }}>
          <Typography color="text.secondary">
            This moves the incident from {incident.status} to {option.to}.
            {selfAssign && ' It will be assigned to you.'}
            {option.to === 'Closed' && ' A closed incident cannot be reopened.'}
          </Typography>
          {formError && <Alert severity="error">{formError}</Alert>}
          {adminAssign && (
            <SelectField
              id="assignee_id"
              label="Engineer"
              value={values.assignee_id ?? ''}
              onChange={handleChange}
              error={fieldErrors.assignee_id}
              disabled={engineers === null}
              helperText={engineers?.length === 0 ? 'No active engineers to assign.' : undefined}
            >
              <option value="">{engineers === null ? 'Loading engineers' : 'Choose an engineer'}</option>
              {(engineers ?? []).map((engineer) => (
                <option key={engineer.id} value={engineer.id}>
                  {engineer.full_name}
                </option>
              ))}
            </SelectField>
          )}
          {textFields.map((name) => (
            <Field
              key={name}
              id={name}
              label={COPY[name].label}
              helperText={COPY[name].help}
              multiline
              minRows={3}
              autoFocus={!adminAssign}
              value={values[name] ?? ''}
              onChange={handleChange}
              error={fieldErrors[name]}
              inputAttributes={{ maxLength: 4000 }}
            />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" variant="contained" disabled={submitting}>
          {submitting ? 'Saving…' : option.label}
        </Button>
      </DialogActions>
    </form>
  )
}

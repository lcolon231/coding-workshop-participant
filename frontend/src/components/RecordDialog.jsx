import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Field from './Field'
import SelectField from './SelectField'
import { focusFirstError, splitDetails } from '../lib/formErrors'
import { ApiError } from '../services/api'

/**
 * One form dialog for every facilities record.
 *
 * `fields` describes the inputs: `{ name, label, type, required, options,
 * multiline, helperText, readOnlyOnEdit, min, max }` where `type` is text,
 * number, select or checkbox. With `initial` the dialog edits: it shows the
 * current values and submits only what changed, because `PUT` is partial.
 * Without, it creates and submits every value that was filled in.
 *
 * Input ids equal field names, so the API's `details[]` can land under the
 * right input and focus it.
 */
export default function RecordDialog({ open, title, description, fields, initial, submitLabel, onSubmit, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      {open && (
        <RecordForm
          title={title}
          description={description}
          fields={fields}
          initial={initial}
          submitLabel={submitLabel}
          onSubmit={onSubmit}
          onClose={onClose}
        />
      )}
    </Dialog>
  )
}

function startingValues(fields, initial) {
  const values = {}
  for (const field of fields) {
    const given = initial?.[field.name]
    if (field.type === 'checkbox') values[field.name] = Boolean(given ?? field.defaultValue ?? false)
    else values[field.name] = given === null || given === undefined ? String(field.defaultValue ?? '') : String(given)
  }
  return values
}

/** What to send: typed to the field, trimmed, empty optional text as `null` when editing. */
function serialise(field, value, editing) {
  if (field.type === 'checkbox') return value
  if (field.type === 'number') return value === '' ? null : Number(value)
  const text = value.trim()
  if (text === '') return editing && !field.required ? null : undefined
  return text
}

/** Mounted fresh each time the dialog opens. */
function RecordForm({ title, description, fields, initial, submitLabel, onSubmit, onClose }) {
  const editing = Boolean(initial)
  const [values, setValues] = useState(() => startingValues(fields, initial))
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const order = fields.map((field) => field.name)

  function setValue(name, value) {
    setValues((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => (current[name] ? { ...current, [name]: undefined } : current))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const errors = {}
    const body = {}
    const before = startingValues(fields, initial)
    for (const field of fields) {
      if (editing && field.readOnlyOnEdit) continue
      const value = values[field.name]
      if (field.required && field.type !== 'checkbox' && String(value).trim() === '') {
        errors[field.name] = 'This is required.'
        continue
      }
      if (field.type === 'number' && value !== '' && !Number.isInteger(Number(value))) {
        errors[field.name] = 'Enter a whole number.'
        continue
      }
      if (editing && value === before[field.name]) continue
      const sent = serialise(field, value, editing)
      if (sent !== undefined) body[field.name] = sent
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      focusFirstError(errors, order)
      return
    }
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
        const { fieldErrors: serverErrors, formErrors } = splitDetails(err.details, order)
        setFieldErrors(serverErrors)
        focusFirstError(serverErrors, order)
        setFormError(formErrors.length > 0 ? formErrors.join(' ') : err.message)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-busy={submitting}>
      <DialogTitle sx={{ fontWeight: 600 }}>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ pt: 1 }}>
          {description && <Typography color="text.secondary">{description}</Typography>}
          {formError && <Alert severity="error">{formError}</Alert>}
          {fields.map((field, index) => {
            const locked = editing && field.readOnlyOnEdit
            const common = {
              id: field.name,
              label: field.label,
              helperText: locked ? field.lockedHelp ?? 'Cannot be changed.' : field.helperText,
              error: fieldErrors[field.name],
              disabled: locked || submitting,
              autoFocus: index === 0 && !locked,
            }
            if (field.type === 'checkbox') {
              return (
                <FormControlLabel
                  key={field.name}
                  control={
                    <Checkbox
                      id={field.name}
                      name={field.name}
                      checked={values[field.name]}
                      onChange={(event) => setValue(field.name, event.target.checked)}
                      disabled={submitting}
                    />
                  }
                  label={field.label}
                />
              )
            }
            if (field.type === 'select') {
              return (
                <SelectField
                  key={field.name}
                  {...common}
                  value={values[field.name]}
                  onChange={(event) => setValue(field.name, event.target.value)}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </SelectField>
              )
            }
            return (
              <Field
                key={field.name}
                {...common}
                type={field.type === 'number' ? 'number' : 'text'}
                multiline={field.multiline}
                minRows={field.multiline ? 2 : undefined}
                value={values[field.name]}
                onChange={(event) => setValue(field.name, event.target.value)}
                inputAttributes={{ maxLength: field.maxLength, min: field.min, max: field.max, step: 1 }}
              />
            )
          })}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" variant="contained" disabled={submitting}>
          {submitting ? 'Saving…' : submitLabel ?? (editing ? 'Save changes' : 'Create')}
        </Button>
      </DialogActions>
    </form>
  )
}

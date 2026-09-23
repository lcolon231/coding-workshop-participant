import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import Field from '../Field'
import { InternalChip } from '../IncidentChips'
import { LoadError } from '../PageState'
import { formatDateTime, formatRelative } from '../../lib/format'
import { ApiError } from '../../services/api'

function Note({ note }) {
  return (
    <Box component="li" sx={{ py: 2, borderBottom: 1, borderColor: 'divider' }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 0.75 }}>
        <Typography sx={{ fontWeight: 500 }}>{note.author.full_name}</Typography>
        <Typography variant="body2" color="text.secondary">
          {note.author.role}
        </Typography>
        {note.visibility === 'internal' && <InternalChip />}
        <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto' }}>
          <time dateTime={note.created_at} title={formatDateTime(note.created_at)}>
            {formatRelative(note.created_at)}
          </time>
        </Typography>
      </Stack>
      <Typography sx={{ whiteSpace: 'pre-wrap' }}>{note.body}</Typography>
    </Box>
  )
}

/**
 * The conversation on an incident, oldest first, and the box to add to it.
 *
 * Staff can mark a note internal; the API refuses that for employees, so the
 * toggle is not even shown to them.
 */
export default function NotesSection({ incident, notes, error, staff, onAdd, onRetry }) {
  const [body, setBody] = useState('')
  const [visibility, setVisibility] = useState('public')
  const [fieldError, setFieldError] = useState(null)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const closed = incident.status === 'Closed'

  async function handleSubmit(event) {
    event.preventDefault()
    if (!body.trim()) {
      setFieldError('Write the note first.')
      document.getElementById('note-body')?.focus()
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      await onAdd({ body: body.trim(), visibility })
      setBody('')
      setVisibility('public')
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack component="section" aria-labelledby="notes-heading" spacing={2}>
      <Typography id="notes-heading" component="h2" variant="h6" sx={{ fontWeight: 600 }}>
        Notes
      </Typography>

      {error ? (
        <LoadError message={error} onRetry={onRetry} />
      ) : notes.length === 0 ? (
        <Typography color="text.secondary">No notes yet.</Typography>
      ) : (
        <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, borderTop: 1, borderColor: 'divider' }}>
          {notes.map((note) => (
            <Note key={note.id} note={note} />
          ))}
        </Box>
      )}

      {closed ? (
        <Typography color="text.secondary">Notes are closed with the incident.</Typography>
      ) : (
        <Stack component="form" noValidate onSubmit={handleSubmit} spacing={2} aria-busy={submitting}>
          {formError && <Alert severity="error">{formError}</Alert>}
          <Field
            id="note-body"
            name="body"
            label="Add a note"
            multiline
            minRows={3}
            value={body}
            onChange={(event) => {
              setBody(event.target.value)
              if (fieldError) setFieldError(null)
            }}
            error={fieldError}
            inputAttributes={{ maxLength: 4000 }}
          />
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
            {staff && (
              <ToggleButtonGroup
                exclusive
                size="small"
                value={visibility}
                onChange={(_, value) => value && setVisibility(value)}
                aria-label="Who can read this note"
              >
                <ToggleButton value="public">Everyone</ToggleButton>
                <ToggleButton value="internal">Staff only</ToggleButton>
              </ToggleButtonGroup>
            )}
            <Button type="submit" variant="outlined" disabled={submitting}>
              {submitting ? 'Adding…' : 'Add note'}
            </Button>
          </Stack>
        </Stack>
      )}
    </Stack>
  )
}

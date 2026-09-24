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
import { ApiError } from '../../services/api'

const VERB = { Approved: 'Approve', Rejected: 'Reject' }

/**
 * An admin's answer to one escalation request, with an optional note.
 *
 * `decision` is "Approved" or "Rejected"; `onSubmit(note)` sends it. The
 * dialog explains what approval does, since it changes the incident's
 * priority the moment it is confirmed.
 */
export default function EscalationDecisionDialog({ open, escalation, decision, onClose, onSubmit }) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="decision-title">
      {open && escalation && (
        <DecisionForm escalation={escalation} decision={decision} onClose={onClose} onSubmit={onSubmit} />
      )}
    </Dialog>
  )
}

function DecisionForm({ escalation, decision, onClose, onSubmit }) {
  const [note, setNote] = useState('')
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const verb = VERB[decision] ?? 'Decide'

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    try {
      await onSubmit(note.trim())
    } catch (err) {
      setSubmitting(false)
      setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-busy={submitting}>
      <DialogTitle id="decision-title" sx={{ fontWeight: 600 }}>
        {verb} escalation
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ pt: 1 }}>
          <Typography color="text.secondary">
            {decision === 'Approved'
              ? `“${escalation.incident_title ?? 'This incident'}” goes up one priority level as soon as you confirm.`
              : `The priority of “${escalation.incident_title ?? 'this incident'}” stays as it is.`}
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {escalation.reason}
          </Typography>
          {formError && <Alert severity="error">{formError}</Alert>}
          <Field
            id="decision-note"
            name="decision_note"
            label="Note"
            helperText="Optional. The requester sees it."
            multiline
            minRows={2}
            autoFocus
            value={note}
            onChange={(event) => setNote(event.target.value)}
            inputAttributes={{ maxLength: 4000 }}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant="contained"
          color={decision === 'Rejected' ? 'error' : 'primary'}
          disabled={submitting}
        >
          {submitting ? `${verb.replace(/e$/, '')}ing…` : verb}
        </Button>
      </DialogActions>
    </form>
  )
}

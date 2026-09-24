import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Field from '../Field'
import EscalationDecisionDialog from './EscalationDecisionDialog'
import { formatDateTime } from '../../lib/format'
import { ApiError } from '../../services/api'

function outcome(item) {
  if (item.status === 'Pending') return 'Awaiting an admin decision'
  return `${item.status} by ${item.decided_by?.full_name ?? 'an admin'}`
}

/**
 * Escalation requests on this incident, and the button to make one.
 *
 * `canRequest` is decided by the page from the same rules the API applies:
 * reporter or assignee, incident still active, not already Critical, none
 * pending. `canDecide` is the admin's side: a pending request gets Approve
 * and Reject, each confirmed in a dialog that takes an optional note.
 */
export default function EscalationPanel({ escalations, canRequest, onRequest, canDecide, onDecide }) {
  const [open, setOpen] = useState(false)
  const [deciding, setDeciding] = useState(null)
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState(null)
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function close() {
    if (submitting) return
    setOpen(false)
    setReason('')
    setFieldError(null)
    setFormError(null)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!reason.trim()) {
      setFieldError('Say why the priority should be raised.')
      document.getElementById('escalation-reason')?.focus()
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      await onRequest(reason.trim())
      setSubmitting(false)
      close()
    } catch (err) {
      setSubmitting(false)
      setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    }
  }

  if (escalations.length === 0 && !canRequest) return null
  const decidable = canDecide ? escalations.filter((item) => item.status === 'Pending') : []

  return (
    <Stack component="section" aria-labelledby="escalation-heading" spacing={1.5}>
      <Typography id="escalation-heading" component="h2" variant="h6" sx={{ fontWeight: 600 }}>
        Escalation
      </Typography>
      {escalations.map((item) => (
        <Box key={item.id}>
          <Typography sx={{ fontWeight: 500 }}>{outcome(item)}</Typography>
          <Typography variant="body2" color="text.secondary">
            Requested by {item.requested_by.full_name}, {formatDateTime(item.created_at)}
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>
            {item.reason}
          </Typography>
          {item.decision_note && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {item.decision_note}
            </Typography>
          )}
          {decidable.includes(item) && (
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Button
                variant="contained"
                size="small"
                onClick={() => setDeciding({ item, decision: 'Approved' })}
              >
                Approve
              </Button>
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={() => setDeciding({ item, decision: 'Rejected' })}
              >
                Reject
              </Button>
            </Stack>
          )}
        </Box>
      ))}
      {canRequest && (
        <Button variant="outlined" onClick={() => setOpen(true)} sx={{ alignSelf: 'flex-start' }}>
          Request escalation
        </Button>
      )}

      <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
        <form noValidate onSubmit={handleSubmit} aria-busy={submitting}>
          <DialogTitle sx={{ fontWeight: 600 }}>Request escalation</DialogTitle>
          <DialogContent>
            <Stack spacing={3} sx={{ pt: 1 }}>
              <Typography color="text.secondary">
                A facility admin will decide. If approved, the priority goes up one level.
              </Typography>
              {formError && <Alert severity="error">{formError}</Alert>}
              <Field
                id="escalation-reason"
                name="reason"
                label="Reason"
                multiline
                minRows={3}
                autoFocus
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value)
                  if (fieldError) setFieldError(null)
                }}
                error={fieldError}
                inputAttributes={{ maxLength: 4000 }}
              />
            </Stack>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2.5 }}>
            <Button onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send request'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      <EscalationDecisionDialog
        open={deciding !== null}
        escalation={deciding?.item}
        decision={deciding?.decision}
        onClose={() => setDeciding(null)}
        onSubmit={async (note) => {
          await onDecide(deciding.item, deciding.decision, note)
          setDeciding(null)
        }}
      />
    </Stack>
  )
}

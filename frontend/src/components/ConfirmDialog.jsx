import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { ApiError } from '../services/api'

/**
 * Ask before an action that is hard to undo, then run it.
 *
 * `onConfirm` is async; while it runs the buttons lock, and if it throws the
 * API's message is shown here rather than the dialog closing. That is where
 * a 409 like "Building has 3 floors; deactivate it instead." belongs: next to
 * the button that caused it.
 */
export default function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  destructive = false,
  onConfirm,
  onClose,
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" aria-labelledby="confirm-title">
      {open && (
        <ConfirmBody
          title={title}
          body={body}
          confirmLabel={confirmLabel}
          destructive={destructive}
          onConfirm={onConfirm}
          onClose={onClose}
        />
      )}
    </Dialog>
  )
}

/** Mounted fresh each time the dialog opens, so an old error never lingers. */
function ConfirmBody({ title, body, confirmLabel, destructive, onConfirm, onClose }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleConfirm() {
    setSubmitting(true)
    setError(null)
    try {
      await onConfirm()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <DialogTitle id="confirm-title" sx={{ fontWeight: 600 }}>
        {title}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {typeof body === 'string' ? <Typography color="text.secondary">{body}</Typography> : body}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color={destructive ? 'error' : 'primary'}
          onClick={handleConfirm}
          disabled={submitting}
        >
          {submitting ? 'Working…' : confirmLabel}
        </Button>
      </DialogActions>
    </>
  )
}

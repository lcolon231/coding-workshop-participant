import Alert from '@mui/material/Alert'
import Snackbar from '@mui/material/Snackbar'

/**
 * The one way a page reports the outcome of a mutation after the fact.
 *
 * `notice` is a string (a success) or `{ message, severity }`. A success is
 * announced politely and goes away by itself; a failure stays until dismissed
 * and is announced as an alert, so it is never mistaken for the confirmation
 * the person was waiting for. Inline forms keep their own field and form
 * errors; this is for actions that have no form of their own.
 */
export default function Notice({ notice, onClose }) {
  const message = typeof notice === 'string' ? notice : notice?.message
  const severity = typeof notice === 'string' ? 'success' : (notice?.severity ?? 'success')
  const failure = severity === 'error' || severity === 'warning'
  return (
    <Snackbar
      open={Boolean(message)}
      autoHideDuration={failure ? null : 4000}
      onClose={(_, reason) => {
        if (reason === 'clickaway') return
        onClose()
      }}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    >
      <Alert
        severity={severity}
        variant="filled"
        role={failure ? 'alert' : 'status'}
        onClose={onClose}
        sx={{ width: '100%', alignItems: 'center' }}
      >
        {message}
      </Alert>
    </Snackbar>
  )
}

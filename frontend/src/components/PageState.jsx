import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Typography from '@mui/material/Typography'

/** A failed load, with the API's message and a way to try again. */
export function LoadError({ message, onRetry }) {
  return (
    <Alert
      severity="error"
      action={
        onRetry && (
          <Button color="inherit" size="small" onClick={onRetry}>
            Try again
          </Button>
        )
      }
    >
      {message}
    </Alert>
  )
}

/** Nothing to show yet: say so, and say what would fill the space. */
export function EmptyState({ icon, title, body, action }) {
  return (
    <Box
      sx={{
        py: { xs: 6, md: 10 },
        px: 2,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        gap: 1.5,
        color: 'text.secondary',
      }}
    >
      {icon}
      <Typography component="h2" variant="h6" color="text.primary" sx={{ fontWeight: 600 }}>
        {title}
      </Typography>
      <Typography sx={{ maxWidth: '44ch' }}>{body}</Typography>
      {action && <Box sx={{ mt: 1 }}>{action}</Box>}
    </Box>
  )
}

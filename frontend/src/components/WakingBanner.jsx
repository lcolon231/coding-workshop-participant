import { useEffect, useState } from 'react'
import Box from '@mui/material/Box'
import LinearProgress from '@mui/material/LinearProgress'
import Paper from '@mui/material/Paper'
import Snackbar from '@mui/material/Snackbar'
import Typography from '@mui/material/Typography'
import { readinessStatus, subscribeReadiness } from '../services/readiness'

/**
 * Says that the database is waking up, for as long as the API client is
 * waiting on it. Sits at the bottom, over whatever loading state the page
 * already shows, so the spinner has a reason.
 */
export default function WakingBanner() {
  const [status, setStatus] = useState(readinessStatus)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => subscribeReadiness(setStatus), [])

  useEffect(() => {
    if (!status.waking) return undefined
    const tick = () => setElapsed(Math.round((Date.now() - status.since) / 1000))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [status])

  return (
    <Snackbar open={status.waking} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Paper
        role="status"
        aria-live="polite"
        elevation={6}
        sx={{ px: 2.5, py: 2, minWidth: { sm: 360 }, maxWidth: 440, borderRadius: 2 }}
      >
        <Typography sx={{ fontWeight: 600 }}>Waking the database</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          It pauses after a quiet period and takes up to a minute to resume. Your request will
          go through by itself once it answers.
        </Typography>
        <Box sx={{ mt: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <LinearProgress sx={{ flex: 1, height: 6, borderRadius: 999 }} aria-hidden="true" />
          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {elapsed}s
          </Typography>
        </Box>
      </Paper>
    </Snackbar>
  )
}

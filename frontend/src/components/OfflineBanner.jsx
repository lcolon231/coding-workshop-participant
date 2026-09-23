import { useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import Snackbar from '@mui/material/Snackbar'

/**
 * Says so when the browser has no connection.
 *
 * The shell still opens offline thanks to the service worker, but nothing
 * behind it does; this tells the person why every list is failing before
 * they try again.
 */
export default function OfflineBanner() {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  return (
    <Snackbar open={!online} anchorOrigin={{ vertical: 'top', horizontal: 'center' }}>
      <Alert severity="warning" variant="filled" role="status" sx={{ width: '100%' }}>
        You are offline. Anything you open now is what was last loaded, and changes will not save until
        the connection is back.
      </Alert>
    </Snackbar>
  )
}

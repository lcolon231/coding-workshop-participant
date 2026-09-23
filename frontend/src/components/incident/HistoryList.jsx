import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { LoadError } from '../PageState'
import { formatDateTime } from '../../lib/format'

/** Every status change, oldest first. */
export default function HistoryList({ history, error, onRetry }) {
  return (
    <Stack component="section" aria-labelledby="history-heading" spacing={2}>
      <Typography id="history-heading" component="h2" variant="h6" sx={{ fontWeight: 600 }}>
        History
      </Typography>
      {error ? (
        <LoadError message={error} onRetry={onRetry} />
      ) : (
        <Box component="ol" sx={{ listStyle: 'none', m: 0, p: 0 }}>
          {history.map((entry) => (
            <Box
              component="li"
              key={entry.id}
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '180px 1fr' },
                columnGap: 3,
                rowGap: 0.5,
                py: 1.5,
                borderBottom: 1,
                borderColor: 'divider',
              }}
            >
              <Typography variant="body2" color="text.secondary" component="time" dateTime={entry.created_at}>
                {formatDateTime(entry.created_at)}
              </Typography>
              <Box>
                <Typography>
                  <Box component="span" sx={{ fontWeight: 500 }}>
                    {entry.from_status ? entry.to_status : 'Reported'}
                  </Box>
                  <Box component="span" sx={{ color: 'text.secondary' }}>
                    {entry.from_status ? ` from ${entry.from_status}, by ` : ' by '}
                    {entry.actor.full_name}
                  </Box>
                </Typography>
                {entry.note && (
                  <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>
                    {entry.note}
                  </Typography>
                )}
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Stack>
  )
}

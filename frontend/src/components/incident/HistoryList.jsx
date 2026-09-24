import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { LoadError } from '../PageState'
import { formatDateTime } from '../../lib/format'

/**
 * What one entry says: the report, a hand-over that left the status alone,
 * or a status change, which may also have handed the incident to someone.
 */
function describe(entry) {
  const by = entry.actor.full_name
  if (!entry.from_status) return { head: 'Reported', rest: ` by ${by}` }
  const handed = entry.assignee ? entry.assignee.full_name : null
  if (handed && entry.from_status === entry.to_status) {
    return { head: 'Assigned', rest: ` to ${handed} by ${by}` }
  }
  return {
    head: entry.to_status,
    rest: ` from ${entry.from_status}, by ${by}${handed ? `, assigned to ${handed}` : ''}`,
  }
}

/** Every status change and assignment, oldest first. */
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
          {history.map((entry) => {
            const { head, rest } = describe(entry)
            return (
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
                      {head}
                    </Box>
                    <Box component="span" sx={{ color: 'text.secondary' }}>
                      {rest}
                    </Box>
                  </Typography>
                  {entry.note && (
                    <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>
                      {entry.note}
                    </Typography>
                  )}
                </Box>
              </Box>
            )
          })}
        </Box>
      )}
    </Stack>
  )
}

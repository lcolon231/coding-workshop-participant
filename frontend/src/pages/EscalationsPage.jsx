import { useCallback, useState } from 'react'
import { Link as RouterLink, useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import Select from '@mui/material/Select'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { visuallyHidden } from '@mui/utils'
import { ArrowFatLinesUp } from '@phosphor-icons/react'
import EscalationDecisionDialog from '../components/incident/EscalationDecisionDialog'
import { PriorityChip, StatusChip } from '../components/IncidentChips'
import Notice from '../components/Notice'
import { EmptyState, LoadError } from '../components/PageState'
import { formatDateTime, formatRelative } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { usePageTitle } from '../lib/usePageTitle'
import { decideEscalation, listEscalationQueue } from '../services/incidents'

const STATUSES = ['Pending', 'Approved', 'Rejected']

const EMPTY = {
  Pending: ['No pending escalations', 'Requests to raise a priority will wait here for a decision.'],
  Approved: ['No approved escalations', 'Approvals in the last 50 will be listed here.'],
  Rejected: ['No rejected escalations', 'Rejections in the last 50 will be listed here.'],
}

function readStatus(params) {
  const value = params.get('status')
  return STATUSES.includes(value) ? value : 'Pending'
}

function Request({ item, onDecide }) {
  const pending = item.status === 'Pending'
  return (
    <Box
      component="li"
      sx={{
        listStyle: 'none',
        p: 2,
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Link
          component={RouterLink}
          to={`/incidents/${item.incident_id}`}
          sx={{ fontWeight: 600, textDecoration: 'none', mr: 'auto' }}
        >
          {item.incident_title}
        </Link>
        <StatusChip status={item.incident_status} />
        <PriorityChip priority={item.incident_priority} />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Requested by {item.requested_by.full_name},{' '}
        <time dateTime={item.created_at} title={formatDateTime(item.created_at)}>
          {formatRelative(item.created_at)}
        </time>
      </Typography>
      <Typography variant="body2" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
        {item.reason}
      </Typography>
      {pending ? (
        <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
          <Button variant="contained" size="small" onClick={() => onDecide(item, 'Approved')}>
            Approve
          </Button>
          <Button variant="outlined" color="error" size="small" onClick={() => onDecide(item, 'Rejected')}>
            Reject
          </Button>
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {item.status} by {item.decided_by?.full_name ?? 'an admin'}
          {item.decision_note ? `: ${item.decision_note}` : ''}
        </Typography>
      )}
    </Box>
  )
}

/**
 * The admin's escalation queue: every request to raise a priority, oldest
 * first, with Approve and Reject on the pending ones. Deciding here is the
 * same call as deciding on the incident page; this view exists so nothing
 * waits unseen inside an incident nobody has opened.
 */
export default function EscalationsPage() {
  usePageTitle('Escalations')
  const [params, setParams] = useSearchParams()
  const status = readStatus(params)
  const [deciding, setDeciding] = useState(null)
  const [notice, setNotice] = useState(null)

  const load = useCallback(() => listEscalationQueue({ status }), [status])
  const { data, error, loading, reload } = useLoad(load)
  const items = data?.items ?? null

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography component="h1" variant="h1">
          Escalations
        </Typography>
        <Box>
          <Typography component="label" htmlFor="escalation-status" sx={visuallyHidden}>
            Status
          </Typography>
          <Select
            native
            size="small"
            id="escalation-status"
            value={status}
            onChange={(event) => setParams({ status: event.target.value }, { replace: true })}
            sx={{ minWidth: 160, '& .MuiSelect-select': { py: 1.25 } }}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </Box>
      </Stack>

      {error && <LoadError message={error} onRetry={reload} />}
      {items === null && !error ? (
        <Stack spacing={1.5} aria-busy="true" aria-label="Loading escalations">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} variant="rounded" height={120} />
          ))}
        </Stack>
      ) : items?.length === 0 ? (
        <EmptyState icon={<ArrowFatLinesUp size={40} />} title={EMPTY[status][0]} body={EMPTY[status][1]} />
      ) : (
        items && (
          <Stack component="ul" spacing={1.5} aria-busy={loading} sx={{ m: 0, p: 0, opacity: loading ? 0.6 : 1 }}>
            {items.map((item) => (
              <Request key={item.id} item={item} onDecide={(target, decision) => setDeciding({ item: target, decision })} />
            ))}
          </Stack>
        )
      )}

      <EscalationDecisionDialog
        open={deciding !== null}
        escalation={deciding?.item}
        decision={deciding?.decision}
        onClose={() => setDeciding(null)}
        onSubmit={async (note) => {
          const decided = await decideEscalation(deciding.item.id, { decision: deciding.decision, decision_note: note })
          setDeciding(null)
          setNotice(
            deciding.decision === 'Approved'
              ? `Escalation approved. “${decided.incident_title}” is now ${decided.incident_priority}.`
              : `Escalation rejected for “${decided.incident_title}”.`,
          )
          reload()
        }}
      />
      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

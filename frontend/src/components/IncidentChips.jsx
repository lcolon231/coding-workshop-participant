import Chip from '@mui/material/Chip'
import { formatDateTime } from '../lib/format'
import { PRIORITY_COLOR, SLA_COLOR, STATUS_COLOR, slaLabel } from '../lib/incidents'

const base = { size: 'small', variant: 'outlined', sx: { fontWeight: 500 } }

export function StatusChip({ status }) {
  return <Chip {...base} label={status} color={STATUS_COLOR[status] ?? 'default'} />
}

export function PriorityChip({ priority }) {
  return <Chip {...base} label={priority} color={PRIORITY_COLOR[priority] ?? 'default'} />
}

/**
 * Where the incident stands against its response target: a countdown while
 * it is open, the verdict once it is finished. The exact deadline is the
 * tooltip. Nothing is drawn for a row served without the field.
 */
export function SlaChip({ incident, now }) {
  if (!incident?.sla_state) return null
  return (
    <Chip
      {...base}
      label={slaLabel(incident, now)}
      color={SLA_COLOR[incident.sla_state] ?? 'default'}
      variant={incident.sla_state === 'breached' ? 'filled' : 'outlined'}
      title={`Target ${formatDateTime(incident.due_at)}`}
    />
  )
}

/** A visibility marker on a note that only staff can read. */
export function InternalChip() {
  return <Chip {...base} label="Internal" />
}

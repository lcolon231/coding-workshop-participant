import Chip from '@mui/material/Chip'
import { PRIORITY_COLOR, STATUS_COLOR } from '../lib/incidents'

const base = { size: 'small', variant: 'outlined', sx: { fontWeight: 500 } }

export function StatusChip({ status }) {
  return <Chip {...base} label={status} color={STATUS_COLOR[status] ?? 'default'} />
}

export function PriorityChip({ priority }) {
  return <Chip {...base} label={priority} color={PRIORITY_COLOR[priority] ?? 'default'} />
}

/** A visibility marker on a note that only staff can read. */
export function InternalChip() {
  return <Chip {...base} label="Internal" />
}

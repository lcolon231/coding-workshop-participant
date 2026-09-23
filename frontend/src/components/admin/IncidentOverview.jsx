import { useCallback, useState } from 'react'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { formatDuration } from '../../lib/format'
import { RANGE_PRESETS, rangeEnding } from '../../lib/reports'
import { useLoad } from '../../lib/useLoad'
import { fetchBuildings, fetchEngineers } from '../../services/reports'
import BarList from '../charts/BarList'
import { EmptyState, LoadError } from '../PageState'

const DEFAULT_DAYS = 30

/** The rows re-ranked by one count, largest first, as bar-list items. */
function ranked(rows, label, count) {
  return [...rows].sort((a, b) => count(b) - count(a)).map((row) => ({ key: label(row), count: count(row) }))
}

function Section({ id, title, children }) {
  return (
    <Box component="section" aria-labelledby={id}>
      <Typography component="h3" variant="h6" id={id} sx={{ fontWeight: 600, mb: 2 }}>
        {title}
      </Typography>
      {children}
    </Box>
  )
}

function EngineerTable({ rows }) {
  return (
    <Table size="small" aria-label="Engineer workload">
      <TableHead>
        <TableRow>
          <TableCell>Engineer</TableCell>
          <TableCell align="right">Assigned</TableCell>
          <TableCell align="right">Open</TableCell>
          <TableCell align="right">Completed</TableCell>
          <TableCell align="right">Resolved, mean</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.engineer_id}>
            <TableCell sx={{ fontWeight: 500 }}>
              {row.engineer}
              {!row.is_active && (
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1, fontWeight: 400 }}>
                  Deactivated
                </Typography>
              )}
            </TableCell>
            <TableCell align="right">{row.assigned_count}</TableCell>
            <TableCell align="right">{row.open_count}</TableCell>
            <TableCell align="right">{row.completed_count}</TableCell>
            <TableCell align="right">{formatDuration(row.mean_resolve_seconds)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * The admin's view over the list: which buildings generate the incidents,
 * and what each engineer holds and has completed, over the last 7, 30 or
 * 90 days. Each half loads and retries on its own.
 */
export default function IncidentOverview() {
  const [days, setDays] = useState(DEFAULT_DAYS)
  const { from, to } = rangeEnding(new Date(), days)
  const loadBuildings = useCallback(() => fetchBuildings({ from, to }), [from, to])
  const loadEngineers = useCallback(() => fetchEngineers({ from, to }), [from, to])
  const buildings = useLoad(loadBuildings)
  const engineers = useLoad(loadEngineers)

  const buildingRows = buildings.data?.rows ?? []
  const buildingsTotal = buildingRows.reduce((sum, row) => sum + row.count, 0)
  const engineerRows = engineers.data?.rows ?? []
  const engineersTotal = engineerRows.reduce((sum, row) => sum + row.assigned_count, 0)

  return (
    <Box component="section" aria-labelledby="overview-heading" sx={{ p: { xs: 2, md: 3 }, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper' }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        useFlexGap
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', flexWrap: 'wrap', mb: 3 }}
      >
        <Typography component="h2" variant="h6" id="overview-heading" sx={{ fontWeight: 600 }}>
          Overview
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }} role="group" aria-label="Overview range">
          {RANGE_PRESETS.map((option) => {
            const selected = option.days === days
            return (
              <Chip
                key={option.days}
                label={option.label}
                clickable
                size="small"
                color={selected ? 'primary' : 'default'}
                variant={selected ? 'filled' : 'outlined'}
                aria-pressed={selected}
                onClick={() => setDays(option.days)}
              />
            )
          })}
        </Stack>
      </Stack>

      <Stack spacing={4}>
        <Section id="overview-buildings" title="Buildings">
          {buildings.error && (
            <Box sx={{ mb: 2 }}>
              <LoadError message={buildings.error} onRetry={buildings.reload} />
            </Box>
          )}
          {buildings.data === null ? (
            !buildings.error && <Skeleton variant="rounded" height={120} />
          ) : buildingsTotal === 0 ? (
            <EmptyState title="No incidents in this range" body="Buildings rank by incidents once something has been reported." />
          ) : (
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 4, opacity: buildings.loading ? 0.6 : 1 }}>
              <BarList title="Most incidents" items={buildingRows.map((row) => ({ key: row.building, count: row.count }))} />
              <BarList title="Still open" items={ranked(buildingRows, (row) => row.building, (row) => row.open_count)} />
              <BarList title="Critical" items={ranked(buildingRows, (row) => row.building, (row) => row.critical_count)} />
            </Box>
          )}
        </Section>

        <Section id="overview-engineers" title="Engineers">
          {engineers.error && (
            <Box sx={{ mb: 2 }}>
              <LoadError message={engineers.error} onRetry={engineers.reload} />
            </Box>
          )}
          {engineers.data === null ? (
            !engineers.error && <Skeleton variant="rounded" height={160} />
          ) : engineerRows.length === 0 ? (
            <EmptyState title="No engineers yet" body="Workload appears once an engineer has an account." />
          ) : (
            <Stack spacing={3} sx={{ opacity: engineers.loading ? 0.6 : 1 }}>
              {engineersTotal > 0 && (
                <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 4 }}>
                  <BarList title="Completed" items={engineerRows.map((row) => ({ key: row.engineer, count: row.completed_count }))} />
                  <BarList title="Open workload" items={ranked(engineerRows, (row) => row.engineer, (row) => row.open_count)} />
                </Box>
              )}
              <Box sx={{ overflowX: 'auto' }}>
                <EngineerTable rows={engineerRows} />
              </Box>
            </Stack>
          )}
        </Section>
      </Stack>
    </Box>
  )
}

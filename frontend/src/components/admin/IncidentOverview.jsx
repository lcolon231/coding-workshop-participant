import { useCallback, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
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
import { RANGE_PRESETS, buildingBars, engineerBars, rangeEnding } from '../../lib/reports'
import { useLoad } from '../../lib/useLoad'
import { listEngineers } from '../../services/facilities'
import { fetchBuildings, fetchEngineers } from '../../services/reports'
import PieChart from '../charts/PieChart'
import StackedBars from '../charts/StackedBars'
import { EmptyState, LoadError } from '../PageState'

const DEFAULT_DAYS = 30

/**
 * Stacked-bar rows as pie slices: one per row, its total the value, its
 * segments the tooltip detail, its colour pinned by `slots` (a map from row
 * key to slot) so the same thing keeps its hue across charts.
 */
function slicesOf(rows, series, slots) {
  return rows.map((row) => ({
    key: row.key,
    label: row.label,
    role: row.role,
    value: row.total,
    slot: slots.get(row.key),
    detail: series.map((entry) => ({ name: entry.name, value: row.values[entry.name] })),
  }))
}

function Section({ id, title, action, children }) {
  return (
    <Box component="section" aria-labelledby={id}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography component="h3" variant="h6" id={id} sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {action}
      </Stack>
      {children}
    </Box>
  )
}

function TableToggle({ on, onToggle }) {
  return (
    <Button size="small" variant="outlined" onClick={onToggle} aria-pressed={on} sx={{ minHeight: 32 }}>
      {on ? 'View as chart' : 'View as table'}
    </Button>
  )
}

function EngineerTable({ rows }) {
  return (
    <Table size="small" aria-label="Engineer workload">
      <TableHead>
        <TableRow>
          <TableCell>Engineer</TableCell>
          <TableCell>Role</TableCell>
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
            <TableCell sx={{ color: row.specialty ? 'text.primary' : 'text.secondary' }}>{row.specialty ?? '—'}</TableCell>
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

/** The engineers marked available right now, lightest load first. */
function loadAvailable() {
  return listEngineers({ is_available: true, sort: 'open_assignments', order: 'asc' })
}

function AvailableEngineers() {
  const { data, loading, error, reload } = useLoad(loadAvailable)
  const items = data?.items ?? null

  return (
    <Section id="overview-available" title="Available now">
      {error && (
        <Box sx={{ mb: 2 }}>
          <LoadError message={error} onRetry={reload} />
        </Box>
      )}
      {items === null ? (
        !error && <Skeleton variant="rounded" height={72} />
      ) : items.length === 0 ? (
        <EmptyState title="Nobody is available" body="Engineers marked available for new assignments appear here with their role and load." />
      ) : (
        <Box
          component="ul"
          aria-label="Available engineers"
          sx={{
            listStyle: 'none',
            m: 0,
            p: 0,
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(auto-fill, minmax(220px, 1fr))' },
            gap: 1.5,
            opacity: loading ? 0.6 : 1,
          }}
        >
          {items.map((engineer) => {
            const full = engineer.open_assignments >= engineer.max_concurrent_incidents
            return (
              <Box
                component="li"
                key={engineer.user_id}
                sx={{ px: 1.5, py: 1.25, border: 1, borderColor: 'divider', borderRadius: 1, minWidth: 0 }}
              >
                <Typography variant="body2" noWrap sx={{ fontWeight: 500 }}>
                  {engineer.user.full_name}
                </Typography>
                <Typography variant="body2" color="text.secondary" noWrap>
                  {engineer.specialty}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ mt: 0.5, fontVariantNumeric: 'tabular-nums', color: full ? 'warning.main' : 'text.secondary' }}
                >
                  {engineer.open_assignments} of {engineer.max_concurrent_incidents} open
                  {full ? ', at capacity' : ''}
                </Typography>
              </Box>
            )
          })}
        </Box>
      )}
    </Section>
  )
}

/**
 * The admin's view over the list: which buildings generate the incidents,
 * and what each engineer holds and has completed, over the last 7, 30 or
 * 90 days. Each half loads and retries on its own.
 *
 * Each chart is a donut of the share per building or engineer, with the
 * finished/open split in the tooltip; the numbers stay reachable through
 * the table views and the workload table. Engineers carry their role (the
 * profile's specialty) in the legend, the tooltip and the table.
 *
 * Below the engineers sits who is available for new work right now. That
 * is live, not a report, so it ignores the range.
 */
export default function IncidentOverview() {
  const [days, setDays] = useState(DEFAULT_DAYS)
  const [buildingsTable, setBuildingsTable] = useState(false)
  const [engineersTable, setEngineersTable] = useState(false)
  const { from, to } = rangeEnding(new Date(), days)
  const loadBuildings = useCallback(() => fetchBuildings({ from, to }), [from, to])
  const loadEngineers = useCallback(() => fetchEngineers({ from, to }), [from, to])
  const buildings = useLoad(loadBuildings)
  const engineers = useLoad(loadEngineers)

  const buildingRows = buildings.data?.rows ?? []
  const buildingsTotal = buildingRows.reduce((sum, row) => sum + row.count, 0)
  const engineerRows = engineers.data?.rows ?? []
  const engineersTotal = engineerRows.reduce((sum, row) => sum + row.assigned_count, 0)
  const buildingChart = buildingBars(buildingRows)
  const engineerChart = engineerBars(engineerRows)
  const critical = [{ name: 'Critical', value: (row) => row.critical }]
  // Colour by building rank in the main chart, so the critical chart matches.
  const buildingSlots = new Map(buildingChart.rows.map((row, index) => [row.key, index]))
  const engineerSlots = new Map(engineerChart.rows.map((row, index) => [row.key, index]))
  const criticalSlices = buildingChart.rows.map((row) => ({ key: row.key, label: row.label, value: row.critical, slot: buildingSlots.get(row.key) }))

  return (
    <Box component="section" aria-labelledby="overview-heading" sx={{ p: { xs: 2, md: 3 }, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', boxShadow: 1 }}>
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
        <Section
          id="overview-buildings"
          title="Buildings"
          action={buildingsTotal > 0 && <TableToggle on={buildingsTable} onToggle={() => setBuildingsTable((v) => !v)} />}
        >
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
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: buildingsTable ? '1fr' : '1fr 1fr' }, gap: 4, opacity: buildings.loading ? 0.6 : 1 }}>
              {buildingsTable ? (
                <StackedBars rows={buildingChart.rows} series={buildingChart.series} extras={critical} table tableLabel="Building" />
              ) : (
                <>
                  <PieChart
                    slices={slicesOf(buildingChart.rows, buildingChart.series, buildingSlots)}
                    ariaLabel="Incidents per building, finished and still open"
                  />
                  <Box component="section" aria-labelledby="overview-critical" sx={{ minWidth: 0 }}>
                    <Typography component="h4" variant="body1" id="overview-critical" sx={{ fontWeight: 600, mb: 1.5 }}>
                      Critical
                    </Typography>
                    {criticalSlices.some((slice) => slice.value > 0) ? (
                      <PieChart slices={criticalSlices} ariaLabel="Critical incidents per building" unit="critical" />
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        Nothing in this range.
                      </Typography>
                    )}
                  </Box>
                </>
              )}
            </Box>
          )}
        </Section>

        <Section
          id="overview-engineers"
          title="Engineers"
          action={engineersTotal > 0 && <TableToggle on={engineersTable} onToggle={() => setEngineersTable((v) => !v)} />}
        >
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
              {engineersTotal > 0 && !engineersTable && (
                <PieChart
                  slices={slicesOf(engineerChart.rows, engineerChart.series, engineerSlots)}
                  ariaLabel="Incidents per engineer, completed and still open"
                />
              )}
              {(engineersTotal === 0 || engineersTable) && (
                <Box sx={{ overflowX: 'auto' }}>
                  <EngineerTable rows={engineerRows} />
                </Box>
              )}
            </Stack>
          )}
        </Section>

        <AvailableEngineers />
      </Stack>
    </Box>
  )
}

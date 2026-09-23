import { useCallback, useMemo, useState } from 'react'
import { Link as RouterLink, useSearchParams } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import LinearProgress from '@mui/material/LinearProgress'
import Link from '@mui/material/Link'
import OutlinedInput from '@mui/material/OutlinedInput'
import Pagination from '@mui/material/Pagination'
import Select from '@mui/material/Select'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import BarList from '../components/charts/BarList'
import StackedColumns from '../components/charts/StackedColumns'
import StatTile from '../components/charts/StatTile'
import { PriorityChip, StatusChip } from '../components/IncidentChips'
import Notice from '../components/Notice'
import { EmptyState, LoadError } from '../components/PageState'
import { saveTextFile } from '../lib/download'
import { formatDate, formatDuration, formatPercent } from '../lib/format'
import { PAGE_SIZE } from '../lib/incidents'
import {
  INTERVALS,
  RANGE_PRESETS,
  SLA_GROUPS,
  VOLUME_GROUPS,
  buildSeries,
  collectAll,
  countOf,
  defaultRange,
  exportFilename,
  incidentsCsv,
  openBacklog,
  pivotVolume,
  presetFor,
  rangeEnding,
} from '../lib/reports'
import { useLoad } from '../lib/useLoad'
import { listBuildings } from '../services/facilities'
import { listIncidents } from '../services/incidents'
import { fetchBuildings, fetchEngineers, fetchSla, fetchSummary, fetchVolume } from '../services/reports'

const selectSx = { minWidth: { xs: '100%', sm: 160 }, '& .MuiSelect-select': { py: 1 } }

function Control({ id, label, children }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Typography component="label" htmlFor={id} variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
        {label}
      </Typography>
      {children}
    </Stack>
  )
}

function ControlSelect({ id, label, value, onChange, children }) {
  return (
    <Control id={id} label={label}>
      <Select
        native
        size="small"
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        input={<OutlinedInput />}
        sx={selectSx}
      >
        {children}
      </Select>
    </Control>
  )
}

function Section({ id, title, children, controls }) {
  return (
    <Box component="section" aria-labelledby={id}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        useFlexGap
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mb: 2, flexWrap: 'wrap' }}
      >
        <Typography component="h2" variant="h6" id={id} sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {controls && (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
            {controls}
          </Stack>
        )}
      </Stack>
      {children}
    </Box>
  )
}

function Frame({ height = 120 }) {
  return <Skeleton variant="rounded" height={height} />
}

/** A date stamp in a table cell, or a dash when it has not happened. */
function Stamp({ iso }) {
  if (!iso) {
    return (
      <Typography component="span" variant="body2" color="text.secondary">
        —
      </Typography>
    )
  }
  return <time dateTime={iso}>{formatDate(iso)}</time>
}

function EngineerTable({ rows, loading }) {
  return (
    <Table size="small" aria-label="Engineer workload" aria-busy={loading}>
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

function IncidentRows({ items, buildingNames }) {
  if (items === null) {
    return Array.from({ length: 5 }, (_, i) => (
      <TableRow key={i}>
        {Array.from({ length: 7 }, (_, j) => (
          <TableCell key={j}>
            <Skeleton width={j === 0 ? '70%' : 64} />
          </TableCell>
        ))}
      </TableRow>
    ))
  }
  return items.map((incident) => (
    <TableRow key={incident.id} hover>
      <TableCell sx={{ maxWidth: 360 }}>
        <Link component={RouterLink} to={`/incidents/${incident.id}`} sx={{ fontWeight: 500, textDecoration: 'none' }}>
          {incident.title}
        </Link>
        <Typography variant="body2" color="text.secondary" noWrap>
          {incident.reporter.full_name}
        </Typography>
      </TableCell>
      <TableCell>
        <StatusChip status={incident.status} />
      </TableCell>
      <TableCell>
        <PriorityChip priority={incident.priority} />
      </TableCell>
      <TableCell>{buildingNames.get(incident.building_id) ?? '—'}</TableCell>
      <TableCell sx={{ color: incident.assignee ? 'text.primary' : 'text.secondary' }}>
        {incident.assignee?.full_name ?? 'Unassigned'}
      </TableCell>
      <TableCell>
        <Stamp iso={incident.created_at} />
      </TableCell>
      <TableCell>
        <Stamp iso={incident.resolved_at} />
      </TableCell>
    </TableRow>
  ))
}

/**
 * The admin dashboard: what came in, how fast it was handled, how the
 * backlog looks, which buildings and engineers carry the load, and every
 * incident behind the numbers, over a date range and optionally one building.
 *
 * Every control lives in the URL. Each report loads on its own, so a failure
 * in one leaves the others standing with their own retry. The CSV export
 * walks the same list the table shows, page by page, and hands over one file.
 */
export default function ReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const fallback = useMemo(() => defaultRange(), [])
  const from = searchParams.get('from') ?? fallback.from
  const to = searchParams.get('to') ?? fallback.to
  const range = { from, to }
  const buildingId = searchParams.get('building') ?? ''
  const slaGroup = SLA_GROUPS.some((g) => g.value === searchParams.get('sla')) ? searchParams.get('sla') : 'priority'
  const interval = INTERVALS.some((i) => i.value === searchParams.get('interval')) ? searchParams.get('interval') : 'day'
  const volumeGroup = VOLUME_GROUPS.some((g) => g.value === searchParams.get('group')) ? searchParams.get('group') : 'status'
  const [volumeTable, setVolumeTable] = useState(false)
  const pageNumber = Math.max(1, Number.parseInt(searchParams.get('page') ?? '1', 10) || 1)
  const [exporting, setExporting] = useState(false)
  const [notice, setNotice] = useState(null)
  const rangeInvalid = range.from > range.to
  const preset = presetFor(range)

  function update(changes) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    // A new window or building starts the incident list from its first page.
    if (!('page' in changes)) next.delete('page')
    setSearchParams(next)
  }

  const loadSummary = useCallback(() => fetchSummary({ from, to, building_id: buildingId }), [from, to, buildingId])
  const loadSla = useCallback(
    () => fetchSla({ from, to, building_id: buildingId, group_by: slaGroup }),
    [from, to, buildingId, slaGroup],
  )
  const loadVolume = useCallback(
    () => fetchVolume({ from, to, building_id: buildingId, interval, group_by: volumeGroup }),
    [from, to, buildingId, interval, volumeGroup],
  )
  const loadByBuilding = useCallback(() => fetchBuildings({ from, to, building_id: buildingId }), [from, to, buildingId])
  const loadEngineers = useCallback(() => fetchEngineers({ from, to, building_id: buildingId }), [from, to, buildingId])
  const listParams = useCallback(
    ({ limit, offset, order = 'desc' }) =>
      listIncidents({
        created_from: from,
        created_to: to,
        building_id: buildingId,
        sort: 'created_at',
        order,
        limit,
        offset,
      }),
    [from, to, buildingId],
  )
  const loadIncidents = useCallback(
    () => listParams({ limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE }),
    [listParams, pageNumber],
  )
  const loadBuildings = useCallback(() => listBuildings(), [])
  const summary = useLoad(loadSummary, !rangeInvalid)
  const sla = useLoad(loadSla, !rangeInvalid)
  const volume = useLoad(loadVolume, !rangeInvalid)
  const byBuilding = useLoad(loadByBuilding, !rangeInvalid)
  const engineers = useLoad(loadEngineers, !rangeInvalid)
  const incidents = useLoad(loadIncidents, !rangeInvalid)
  const buildings = useLoad(loadBuildings)

  const series = volume.data ? buildSeries(volumeGroup, volume.data.rows) : []
  const buckets = volume.data ? pivotVolume(volume.data.rows, { ...range, interval, series }) : []
  const volumeTotal = buckets.reduce((sum, bucket) => sum + bucket.total, 0)
  const targets = sla.data?.targets ?? []
  const buildingNames = useMemo(
    () => new Map((buildings.data?.items ?? []).map((building) => [building.id, building.name])),
    [buildings.data],
  )
  const buildingRows = byBuilding.data?.rows ?? []
  const buildingsTotal = buildingRows.reduce((sum, row) => sum + row.count, 0)
  const engineerRows = engineers.data?.rows ?? []
  const engineersTotal = engineerRows.reduce((sum, row) => sum + row.assigned_count, 0)
  const pageCount = incidents.data ? Math.max(1, Math.ceil(incidents.data.total / incidents.data.limit)) : 1

  async function exportCsv() {
    setExporting(true)
    try {
      const items = await collectAll((paging) => listParams({ ...paging, order: 'asc' }))
      saveTextFile(exportFilename(range), incidentsCsv(items, buildingNames))
      setNotice(`Exported ${items.length} incident${items.length === 1 ? '' : 's'}.`)
    } catch (err) {
      setNotice({ message: `Could not export: ${err.message}`, severity: 'error' })
    } finally {
      setExporting(false)
    }
  }

  return (
    <Stack spacing={4}>
      <Box>
        <Typography component="h1" variant="h1">
          Reports
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          Incidents reported from {formatDate(range.from)} to {formatDate(range.to)}
          {buildingId && buildings.data ? `, in ${buildings.data.items.find((b) => b.id === buildingId)?.name ?? 'one building'}` : ''}.
        </Typography>
      </Box>

      <Stack
        component="form"
        role="search"
        aria-label="Report range"
        onSubmit={(event) => event.preventDefault()}
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        useFlexGap
        sx={{ alignItems: { md: 'center' }, flexWrap: 'wrap' }}
      >
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }} role="group" aria-label="Presets">
          {RANGE_PRESETS.map((option) => {
            const selected = preset?.days === option.days
            return (
              <Chip
                key={option.days}
                label={option.label}
                clickable
                color={selected ? 'primary' : 'default'}
                variant={selected ? 'filled' : 'outlined'}
                aria-pressed={selected}
                onClick={() => update(rangeEnding(new Date(), option.days))}
              />
            )
          })}
        </Stack>
        <Control id="from" label="From">
          <OutlinedInput
            id="from"
            type="date"
            size="small"
            value={range.from}
            inputProps={{ max: range.to }}
            onChange={(event) => update({ from: event.target.value })}
            sx={{ '& input': { py: 1 } }}
          />
        </Control>
        <Control id="to" label="To">
          <OutlinedInput
            id="to"
            type="date"
            size="small"
            value={range.to}
            inputProps={{ min: range.from }}
            onChange={(event) => update({ to: event.target.value })}
            sx={{ '& input': { py: 1 } }}
          />
        </Control>
        <ControlSelect id="building" label="Building" value={buildingId} onChange={(v) => update({ building: v })}>
          <option value="">All buildings</option>
          {(buildings.data?.items ?? []).map((building) => (
            <option key={building.id} value={building.id}>
              {building.name}
            </option>
          ))}
        </ControlSelect>
      </Stack>

      {rangeInvalid && <Alert severity="warning">The start of the range is after its end.</Alert>}

      <Section id="summary-heading" title="Summary">
        {summary.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={summary.error} onRetry={summary.reload} />
          </Box>
        )}
        {summary.data === null ? (
          !summary.error && <Frame />
        ) : summary.data.total === 0 ? (
          <EmptyState title="No incidents in this range" body="Widen the range or clear the building filter." />
        ) : (
          <Stack spacing={3} sx={{ opacity: summary.loading ? 0.6 : 1 }}>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 2 }}>
              <StatTile label="Reported" value={summary.data.total} hint="in the range" />
              <StatTile label="Open backlog" value={openBacklog(summary.data)} hint="not yet closed" />
              <StatTile
                label="Resolved or closed"
                value={countOf(summary.data.by_status, 'Resolved') + countOf(summary.data.by_status, 'Closed')}
                hint={formatPercent(
                  (countOf(summary.data.by_status, 'Resolved') + countOf(summary.data.by_status, 'Closed')) / summary.data.total,
                )}
              />
              <StatTile label="Critical" value={countOf(summary.data.by_priority, 'Critical')} hint="highest priority" />
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 4 }}>
              <BarList title="By status" items={summary.data.by_status} />
              <BarList title="By priority" items={summary.data.by_priority} />
              <BarList title="Open backlog by age" items={summary.data.backlog_by_age} />
            </Box>
          </Stack>
        )}
      </Section>

      <Section
        id="sla-heading"
        title="Response times"
        controls={
          <ControlSelect id="sla-group" label="By" value={slaGroup} onChange={(v) => update({ sla: v === 'priority' ? null : v })}>
            {SLA_GROUPS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </ControlSelect>
        }
      >
        {sla.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={sla.error} onRetry={sla.reload} />
          </Box>
        )}
        {sla.data === null ? (
          !sla.error && <Frame height={160} />
        ) : sla.data.rows.length === 0 ? (
          <EmptyState title="No incidents in this range" body="Response times appear once something has been reported." />
        ) : (
          <Box sx={{ overflowX: 'auto', opacity: sla.loading ? 0.6 : 1 }}>
            <Table size="small" aria-label="Response times">
              <TableHead>
                <TableRow>
                  <TableCell>{SLA_GROUPS.find((g) => g.value === slaGroup)?.label}</TableCell>
                  <TableCell align="right">Incidents</TableCell>
                  <TableCell align="right">Resolved</TableCell>
                  <TableCell align="right">Acknowledged, mean</TableCell>
                  <TableCell align="right">p90</TableCell>
                  <TableCell align="right">Resolved, mean</TableCell>
                  <TableCell align="right">p90</TableCell>
                  <TableCell sx={{ minWidth: 160 }}>Within target</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sla.data.rows.map((row) => (
                  <TableRow key={row.group}>
                    <TableCell sx={{ fontWeight: 500 }}>{row.group}</TableCell>
                    <TableCell align="right">{row.count}</TableCell>
                    <TableCell align="right">{row.resolved_count}</TableCell>
                    <TableCell align="right">{formatDuration(row.mean_ack_seconds)}</TableCell>
                    <TableCell align="right">{formatDuration(row.p90_ack_seconds)}</TableCell>
                    <TableCell align="right">{formatDuration(row.mean_resolve_seconds)}</TableCell>
                    <TableCell align="right">{formatDuration(row.p90_resolve_seconds)}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                        <LinearProgress
                          variant="determinate"
                          value={row.within_target_ratio === null ? 0 : row.within_target_ratio * 100}
                          aria-hidden="true"
                          sx={{ flex: 1, height: 8, borderRadius: 999 }}
                        />
                        <Typography variant="body2" sx={{ minWidth: '4ch', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                          {formatPercent(row.within_target_ratio)}
                        </Typography>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {targets.length > 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
                Targets, from report to resolution:{' '}
                {targets.map((target) => `${target.priority} ${formatDuration(target.target_seconds)}`).join(', ')}.
              </Typography>
            )}
          </Box>
        )}
      </Section>

      <Section
        id="volume-heading"
        title="Volume"
        controls={
          <>
            <ControlSelect id="interval" label="Per" value={interval} onChange={(v) => update({ interval: v === 'day' ? null : v })}>
              {INTERVALS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </ControlSelect>
            <ControlSelect id="volume-group" label="Split by" value={volumeGroup} onChange={(v) => update({ group: v === 'status' ? null : v })}>
              {VOLUME_GROUPS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </ControlSelect>
            <Button size="small" variant="outlined" onClick={() => setVolumeTable((v) => !v)} aria-pressed={volumeTable} sx={{ minHeight: 36 }}>
              {volumeTable ? 'View as chart' : 'View as table'}
            </Button>
          </>
        }
      >
        {volume.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={volume.error} onRetry={volume.reload} />
          </Box>
        )}
        {volume.data === null ? (
          !volume.error && <Frame height={260} />
        ) : volumeTotal === 0 ? (
          <EmptyState title="No incidents in this range" body="The chart fills in as incidents are reported." />
        ) : (
          <Box sx={{ opacity: volume.loading ? 0.6 : 1 }}>
            <StackedColumns
              buckets={buckets}
              series={series}
              table={volumeTable}
              ariaLabel={`Incidents reported per ${interval}, split by ${volumeGroup}`}
            />
          </Box>
        )}
      </Section>

      <Section id="buildings-heading" title="Buildings">
        {byBuilding.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={byBuilding.error} onRetry={byBuilding.reload} />
          </Box>
        )}
        {byBuilding.data === null ? (
          !byBuilding.error && <Frame height={160} />
        ) : buildingsTotal === 0 ? (
          <EmptyState title="No incidents in this range" body="Buildings rank by incidents once something has been reported." />
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 4, opacity: byBuilding.loading ? 0.6 : 1 }}>
            <BarList title="Most incidents" items={buildingRows.map((row) => ({ key: row.building, count: row.count }))} />
            <BarList
              title="Still open"
              items={[...buildingRows].sort((a, b) => b.open_count - a.open_count).map((row) => ({ key: row.building, count: row.open_count }))}
            />
            <BarList
              title="Critical"
              items={[...buildingRows].sort((a, b) => b.critical_count - a.critical_count).map((row) => ({ key: row.building, count: row.critical_count }))}
            />
          </Box>
        )}
      </Section>

      <Section id="engineers-heading" title="Engineers">
        {engineers.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={engineers.error} onRetry={engineers.reload} />
          </Box>
        )}
        {engineers.data === null ? (
          !engineers.error && <Frame height={200} />
        ) : engineerRows.length === 0 ? (
          <EmptyState title="No engineers yet" body="Workload appears once an engineer has an account." />
        ) : (
          <Stack spacing={3} sx={{ opacity: engineers.loading ? 0.6 : 1 }}>
            {engineersTotal > 0 && (
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 4 }}>
                <BarList title="Completed" items={engineerRows.map((row) => ({ key: row.engineer, count: row.completed_count }))} />
                <BarList
                  title="Open workload"
                  items={[...engineerRows].sort((a, b) => b.open_count - a.open_count).map((row) => ({ key: row.engineer, count: row.open_count }))}
                />
              </Box>
            )}
            <Box sx={{ overflowX: 'auto' }}>
              <EngineerTable rows={engineerRows} loading={engineers.loading} />
            </Box>
          </Stack>
        )}
      </Section>

      <Section
        id="incidents-heading"
        title="All incidents"
        controls={
          <Button
            size="small"
            variant="outlined"
            onClick={exportCsv}
            disabled={exporting || rangeInvalid || (incidents.data?.total ?? 0) === 0}
            sx={{ minHeight: 36 }}
          >
            {exporting ? 'Exporting…' : 'Download CSV'}
          </Button>
        }
      >
        {incidents.error && (
          <Box sx={{ mb: 2 }}>
            <LoadError message={incidents.error} onRetry={incidents.reload} />
          </Box>
        )}
        {incidents.data !== null && incidents.data.total === 0 ? (
          <EmptyState title="No incidents in this range" body="Every incident reported in the range is listed here." />
        ) : (
          (incidents.data !== null || !incidents.error) && (
            <Box sx={{ opacity: incidents.loading ? 0.6 : 1 }}>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small" aria-label="All incidents" aria-busy={incidents.loading}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Title</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Priority</TableCell>
                      <TableCell>Building</TableCell>
                      <TableCell>Assignee</TableCell>
                      <TableCell>Reported</TableCell>
                      <TableCell>Resolved</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <IncidentRows items={incidents.data?.items ?? null} buildingNames={buildingNames} />
                  </TableBody>
                </Table>
              </Box>
              {incidents.data && (
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5}
                  sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mt: 2 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    Showing {incidents.data.offset + 1}–{incidents.data.offset + incidents.data.items.length} of {incidents.data.total}
                  </Typography>
                  {pageCount > 1 && (
                    <Pagination
                      count={pageCount}
                      page={Math.min(pageNumber, pageCount)}
                      onChange={(_, value) => update({ page: value === 1 ? null : String(value) })}
                      shape="rounded"
                    />
                  )}
                </Stack>
              )}
            </Box>
          )
        )}
      </Section>

      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

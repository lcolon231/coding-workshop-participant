import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import LinearProgress from '@mui/material/LinearProgress'
import OutlinedInput from '@mui/material/OutlinedInput'
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
import { EmptyState, LoadError } from '../components/PageState'
import { formatDate, formatDuration, formatPercent } from '../lib/format'
import {
  INTERVALS,
  RANGE_PRESETS,
  SLA_GROUPS,
  VOLUME_GROUPS,
  buildSeries,
  countOf,
  defaultRange,
  openBacklog,
  pivotVolume,
  presetFor,
  rangeEnding,
} from '../lib/reports'
import { useLoad } from '../lib/useLoad'
import { listBuildings } from '../services/facilities'
import { fetchSla, fetchSummary, fetchVolume } from '../services/reports'

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

/**
 * The admin dashboard: what came in, how fast it was handled, and how the
 * backlog looks, over a date range and optionally one building.
 *
 * Every control lives in the URL. Each of the three reports loads on its
 * own, so a failure in one leaves the others standing with their own retry.
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
  const rangeInvalid = range.from > range.to
  const preset = presetFor(range)

  function update(changes) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
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
  const loadBuildings = useCallback(() => listBuildings(), [])
  const summary = useLoad(loadSummary, !rangeInvalid)
  const sla = useLoad(loadSla, !rangeInvalid)
  const volume = useLoad(loadVolume, !rangeInvalid)
  const buildings = useLoad(loadBuildings)

  const series = volume.data ? buildSeries(volumeGroup, volume.data.rows) : []
  const buckets = volume.data ? pivotVolume(volume.data.rows, { ...range, interval, series }) : []
  const volumeTotal = buckets.reduce((sum, bucket) => sum + bucket.total, 0)
  const targets = sla.data?.targets ?? []

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
    </Stack>
  )
}

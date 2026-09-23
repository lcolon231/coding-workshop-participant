import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useLocation, useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import InputAdornment from '@mui/material/InputAdornment'
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
import { visuallyHidden } from '@mui/utils'
import { ClipboardText, MagnifyingGlass } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthContext'
import IncidentOverview from '../components/admin/IncidentOverview'
import { PriorityChip, StatusChip } from '../components/IncidentChips'
import Notice from '../components/Notice'
import { EmptyState, LoadError } from '../components/PageState'
import { saveTextFile } from '../lib/download'
import { formatDateTime, formatRelative, isoDate } from '../lib/format'
import { PAGE_SIZE, PRIORITIES, SORT_OPTIONS, STATUSES, isAdmin } from '../lib/incidents'
import { collectAll, incidentsCsv } from '../lib/reports'
import { useWide } from '../lib/useViewport'
import { listBuildings } from '../services/facilities'
import { listIncidents } from '../services/incidents'

const DEFAULT_SORT = SORT_OPTIONS[0].value

/** The filters live in the URL, so a view can be shared and the back button works. */
function readFilters(params) {
  const page = Number.parseInt(params.get('page') ?? '1', 10)
  return {
    status: params.get('status') ?? '',
    priority: params.get('priority') ?? '',
    search: params.get('search') ?? '',
    sort: params.get('sort') ?? DEFAULT_SORT,
    mine: params.get('mine') === '1',
    page: Number.isFinite(page) && page > 0 ? page : 1,
  }
}

function hasFilters(filters) {
  return Boolean(filters.status || filters.priority || filters.search || filters.mine)
}

const selectSx = { minWidth: { xs: '100%', sm: 160 }, '& .MuiSelect-select': { py: 1.25 } }

function FilterSelect({ id, label, value, onChange, children }) {
  return (
    <Box>
      <Typography component="label" htmlFor={id} sx={visuallyHidden}>
        {label}
      </Typography>
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
    </Box>
  )
}

function RowSkeleton() {
  return (
    <TableRow>
      <TableCell>
        <Skeleton width="60%" />
      </TableCell>
      <TableCell>
        <Skeleton width={72} />
      </TableCell>
      <TableCell>
        <Skeleton width={64} />
      </TableCell>
      <TableCell>
        <Skeleton width="50%" />
      </TableCell>
      <TableCell>
        <Skeleton width={80} />
      </TableCell>
    </TableRow>
  )
}

function IncidentTable({ items, loading }) {
  return (
    <Table aria-busy={loading} sx={{ opacity: loading ? 0.6 : 1 }}>
      <TableHead>
        <TableRow>
          <TableCell>Title</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Priority</TableCell>
          <TableCell>Assignee</TableCell>
          <TableCell>Reported</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items === null
          ? Array.from({ length: 6 }, (_, i) => <RowSkeleton key={i} />)
          : items.map((incident) => (
              <TableRow key={incident.id} hover>
                <TableCell sx={{ maxWidth: 480 }}>
                  <Link
                    component={RouterLink}
                    to={`/incidents/${incident.id}`}
                    sx={{ fontWeight: 500, textDecoration: 'none' }}
                  >
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
                <TableCell sx={{ color: incident.assignee ? 'text.primary' : 'text.secondary' }}>
                  {incident.assignee?.full_name ?? 'Unassigned'}
                </TableCell>
                <TableCell>
                  <time dateTime={incident.created_at} title={formatDateTime(incident.created_at)}>
                    {formatRelative(incident.created_at)}
                  </time>
                </TableCell>
              </TableRow>
            ))}
      </TableBody>
    </Table>
  )
}

/** Below `md` the table becomes a stack of rows: title, chips, then who and when. */
function IncidentCards({ items, loading }) {
  return (
    <Stack
      component="ul"
      aria-busy={loading}
      sx={{ listStyle: 'none', m: 0, p: 0, opacity: loading ? 0.6 : 1 }}
    >
      {items === null
        ? Array.from({ length: 4 }, (_, i) => (
            <Box component="li" key={i} sx={{ py: 2, borderBottom: 1, borderColor: 'divider' }}>
              <Skeleton width="70%" />
              <Skeleton width="40%" />
            </Box>
          ))
        : items.map((incident) => (
            <Box
              component="li"
              key={incident.id}
              sx={{ py: 2, borderBottom: 1, borderColor: 'divider' }}
            >
              <Link
                component={RouterLink}
                to={`/incidents/${incident.id}`}
                sx={{ fontWeight: 500, textDecoration: 'none', display: 'block', mb: 1 }}
              >
                {incident.title}
              </Link>
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <StatusChip status={incident.status} />
                <PriorityChip priority={incident.priority} />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {incident.assignee ? `Assigned to ${incident.assignee.full_name}` : 'Unassigned'}
                {', '}
                <time dateTime={incident.created_at} title={formatDateTime(incident.created_at)}>
                  {formatRelative(incident.created_at)}
                </time>
              </Typography>
            </Box>
          ))}
    </Stack>
  )
}

export default function IncidentsPage() {
  const { user } = useAuth()
  // One layout at a time: the table above `md`, stacked rows below it.
  const wide = useWide()
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const filters = useMemo(() => readFilters(searchParams), [searchParams])
  // The draft is tied to the URL value it was typed over, so a URL change
  // (back button, "Clear filters") replaces it instead of fighting it.
  const [draft, setDraft] = useState({ base: filters.search, text: filters.search })
  const searchText = draft.base === filters.search ? draft.text : filters.search
  const setSearchText = (text) => setDraft({ base: filters.search, text })
  const [attempt, setAttempt] = useState(0)
  const key = `${searchParams.toString()}#${attempt}`
  const [result, setResult] = useState({ key: null, page: null, error: null })
  const [exporting, setExporting] = useState(false)
  // A page that sends someone here after a mutation passes its confirmation in.
  const [notice, setNotice] = useState(location.state?.notice ?? null)
  const admin = isAdmin(user)

  const update = useCallback(
    (changes) => {
      const next = new URLSearchParams(searchParams)
      for (const [key, value] of Object.entries({ page: '1', ...changes })) {
        if (value === '' || value === false || value === null || (key === 'page' && value === '1')) {
          next.delete(key)
        } else {
          next.set(key, value === true ? '1' : String(value))
        }
      }
      setSearchParams(next)
    },
    [searchParams, setSearchParams],
  )

  // Typing is debounced into the URL.
  useEffect(() => {
    if (searchText === filters.search) return undefined
    const timer = setTimeout(() => update({ search: searchText.trim() }), 300)
    return () => clearTimeout(timer)
  }, [searchText, filters.search, update])

  const query = useMemo(
    () => ({
      status: filters.status,
      priority: filters.priority,
      search: filters.search,
      assignee_id: filters.mine ? user.id : '',
    }),
    [filters, user.id],
  )

  useEffect(() => {
    let cancelled = false
    const [sort, order] = filters.sort.split(':')
    listIncidents({
      ...query,
      sort,
      order,
      limit: PAGE_SIZE,
      offset: (filters.page - 1) * PAGE_SIZE,
    })
      .then((page) => {
        if (!cancelled) setResult({ key, page, error: null })
      })
      .catch((err) => {
        if (!cancelled) setResult((current) => ({ key, page: current.page, error: err.message }))
      })
    return () => {
      cancelled = true
    }
  }, [filters, query, key])

  /** Every incident the current filters match, oldest first, as one CSV file. */
  async function exportCsv() {
    setExporting(true)
    try {
      const [buildings, items] = await Promise.all([
        listBuildings(),
        collectAll((paging) => listIncidents({ ...query, sort: 'created_at', order: 'asc', ...paging })),
      ])
      const names = new Map(buildings.items.map((building) => [building.id, building.name]))
      saveTextFile(`incidents-${isoDate(new Date())}.csv`, incidentsCsv(items, names))
      setNotice(`Exported ${items.length} incident${items.length === 1 ? '' : 's'}.`)
    } catch (err) {
      setNotice({ message: `Could not export: ${err.message}`, severity: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const loading = result.key !== key
  const { page } = result
  const error = loading ? null : result.error
  const items = page?.items ?? null
  const pageCount = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1
  const first = page ? page.offset + 1 : 0
  const last = page ? page.offset + page.items.length : 0

  return (
    <Stack spacing={3}>
      <Box>
        <Typography component="h1" variant="h1">
          Incidents
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          {user.role === 'Facility Admin'
            ? 'Everything reported across every building.'
            : user.role === 'Engineer'
              ? 'Work a Facility Admin has assigned to you.'
              : 'Everything you have reported.'}
        </Typography>
      </Box>

      {admin && <IncidentOverview />}

      <Stack
        component="form"
        role="search"
        onSubmit={(event) => event.preventDefault()}
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        useFlexGap
        sx={{ flexWrap: 'wrap', alignItems: { sm: 'center' } }}
      >
        <Box sx={{ flex: { sm: '1 1 240px' } }}>
          <Typography component="label" htmlFor="search" sx={visuallyHidden}>
            Search incidents
          </Typography>
          <OutlinedInput
            id="search"
            type="search"
            fullWidth
            size="small"
            placeholder="Search title or description"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            startAdornment={
              <InputAdornment position="start">
                <MagnifyingGlass size={18} />
              </InputAdornment>
            }
            sx={{ '& input': { py: 1.25 } }}
          />
        </Box>
        <FilterSelect id="status" label="Status" value={filters.status} onChange={(v) => update({ status: v })}>
          <option value="">Any status</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect id="priority" label="Priority" value={filters.priority} onChange={(v) => update({ priority: v })}>
          <option value="">Any priority</option>
          {PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {priority}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect id="sort" label="Sort by" value={filters.sort} onChange={(v) => update({ sort: v, page: String(filters.page) })}>
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </FilterSelect>
        {user.role === 'Engineer' && (
          <FormControlLabel
            control={
              <Checkbox
                checked={filters.mine}
                onChange={(event) => update({ mine: event.target.checked })}
              />
            }
            label="Assigned to me"
            sx={{ mr: 0 }}
          />
        )}
        {admin && (
          <Button
            variant="outlined"
            onClick={exportCsv}
            disabled={exporting || !page || page.total === 0}
            sx={{ minHeight: 40, whiteSpace: 'nowrap', ml: { sm: 'auto' } }}
          >
            {exporting ? 'Exporting…' : 'Download CSV'}
          </Button>
        )}
      </Stack>

      {error && <LoadError message={error} onRetry={() => setAttempt((n) => n + 1)} />}

      {items?.length === 0 ? (
        <EmptyState
          icon={<ClipboardText size={40} />}
          title={hasFilters(filters) ? 'No incidents match' : 'No incidents yet'}
          body={
            hasFilters(filters)
              ? 'Try a different status, priority or search.'
              : 'Report a facility issue and it will appear here with its progress.'
          }
          action={
            hasFilters(filters) ? (
              <Button variant="outlined" onClick={() => setSearchParams({})}>
                Clear filters
              </Button>
            ) : (
              <Button variant="contained" component={RouterLink} to="/incidents/new">
                Report an incident
              </Button>
            )
          }
        />
      ) : (
        <Box>
          {wide ? (
            <IncidentTable items={items} loading={loading} />
          ) : (
            <IncidentCards items={items} loading={loading} />
          )}
          {page && page.total > 0 && (
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              sx={{ mt: 2, alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
            >
              <Typography variant="body2" color="text.secondary" aria-live="polite">
                Showing {first} to {last} of {page.total}
              </Typography>
              {pageCount > 1 && (
                <Pagination
                  count={pageCount}
                  page={Math.min(filters.page, pageCount)}
                  onChange={(_, value) => update({ page: String(value) })}
                  shape="rounded"
                />
              )}
            </Stack>
          )}
        </Box>
      )}

      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

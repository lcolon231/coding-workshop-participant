import { useEffect, useState } from 'react'
import { usePageTitle } from '../lib/usePageTitle'
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { ArrowLeft, MagnifyingGlass } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthContext'
import { PriorityChip, StatusChip } from '../components/IncidentChips'
import { EmptyState, LoadError } from '../components/PageState'
import Notice from '../components/Notice'
import EscalationPanel from '../components/incident/EscalationPanel'
import HistoryList from '../components/incident/HistoryList'
import NotesSection from '../components/incident/NotesSection'
import TransitionDialog from '../components/incident/TransitionDialog'
import TriagePanel from '../components/incident/TriagePanel'
import { formatDateTime, formatRelative } from '../lib/format'
import { FORWARD_TRANSITIONS, canRequestEscalation, isAdmin, isStaff } from '../lib/incidents'
import { useWide } from '../lib/useViewport'
import { ApiError } from '../services/api'
import { listUsers } from '../services/auth'
import { getBuilding, getCategory, getFloor, getSeat } from '../services/facilities'
import {
  createNote,
  getIncident,
  listHistory,
  listIncidentEscalations,
  listNotes,
  requestEscalation,
  transitionIncident,
  updateIncident,
} from '../services/incidents'

function settled(result, fallback) {
  return result.status === 'fulfilled'
    ? { value: result.value, error: null }
    : { value: fallback, error: result.reason?.message ?? 'Could not load.' }
}

function describeLocation(building, floor, seat) {
  const parts = []
  if (building) parts.push(building.name)
  if (floor) parts.push(floor.name ? `${floor.name} (level ${floor.level})` : `level ${floor.level}`)
  if (seat) parts.push(seat.label ? `seat ${seat.code}, ${seat.label}` : `seat ${seat.code}`)
  return parts.join(', ')
}

function Detail({ term, children }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '120px 1fr', columnGap: 2, py: 1 }}>
      <Typography component="dt" variant="body2" color="text.secondary">
        {term}
      </Typography>
      <Typography component="dd" variant="body2" sx={{ m: 0 }}>
        {children}
      </Typography>
    </Box>
  )
}

function Stamp({ iso }) {
  if (!iso) return <Box component="span" sx={{ color: 'text.secondary' }}>Not yet</Box>
  return (
    <time dateTime={iso} title={formatDateTime(iso)}>
      {formatDateTime(iso)}
    </time>
  )
}

/**
 * The workflow buttons. Rendered in the side column on wide screens and
 * under the title on narrow ones, so they never sit below the history.
 */
function ActionsSection({ transitions, onPick }) {
  return (
    <Stack component="section" aria-labelledby="actions-heading" spacing={1.5}>
      <Typography id="actions-heading" component="h2" variant="h6" sx={{ fontWeight: 600 }}>
        Actions
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
        {transitions.map((option) => (
          <Button
            key={option.to}
            variant={FORWARD_TRANSITIONS.has(option.to) ? 'contained' : 'outlined'}
            onClick={() => onPick(option)}
          >
            {option.label}
          </Button>
        ))}
      </Stack>
    </Stack>
  )
}

function PageSkeleton() {
  return (
    <Box aria-busy="true" aria-label="Loading incident">
      <Skeleton width={120} />
      <Skeleton width="55%" height={44} sx={{ mt: 2 }} />
      <Skeleton width="30%" />
      <Skeleton height={120} sx={{ mt: 3 }} />
    </Box>
  )
}

export default function IncidentPage() {
  const { incidentId } = useParams()
  const location = useLocation()
  const { user } = useAuth()
  const admin = isAdmin(user)
  const staff = isStaff(user)
  // Two columns above `md`; below it the actions move up under the title.
  const wide = useWide()

  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState({ key: null, data: null, error: null, status: null })
  const [place, setPlace] = useState({ location: '', category: null })
  const [engineers, setEngineers] = useState(null)
  const [pending, setPending] = useState(null)
  const [notice, setNotice] = useState(location.state?.notice ?? null)

  const key = `${incidentId}#${attempt}`
  useEffect(() => {
    let cancelled = false
    async function load() {
      let incident
      try {
        incident = await getIncident(incidentId)
      } catch (err) {
        if (!cancelled) {
          setResult({
            key,
            data: null,
            error: err.message,
            status: err instanceof ApiError ? err.status : null,
          })
        }
        return
      }
      const [notes, history, escalations] = await Promise.allSettled([
        listNotes(incidentId),
        listHistory(incidentId),
        listIncidentEscalations(incidentId),
      ])
      if (cancelled) return
      setResult({
        key,
        data: {
          incident,
          notes: settled(notes, { items: [] }),
          history: settled(history, { items: [] }),
          escalations: settled(escalations, { items: [] }),
        },
        error: null,
        status: null,
      })
    }
    load()
    return () => {
      cancelled = true
    }
  }, [incidentId, key])

  const loading = result.key !== key
  // While a reload is in flight the previous data stays on screen, dimmed;
  // a different incident's data never does.
  const data = result.key?.startsWith(`${incidentId}#`) ? result.data : null
  const loadError = loading ? null : result.error
  const reload = () => setAttempt((n) => n + 1)

  // Names for the ids the incident carries. Optional: the page reads without them.
  const incident = data?.incident
  usePageTitle(incident?.title ?? 'Incident')
  const buildingId = incident?.building_id
  const floorId = incident?.floor_id
  const seatId = incident?.seat_id
  const categoryId = incident?.category_id
  useEffect(() => {
    if (!buildingId) return undefined
    let cancelled = false
    const maybe = (id, fetcher) => (id ? fetcher(id) : Promise.resolve(null))
    Promise.allSettled([
      getBuilding(buildingId),
      maybe(floorId, getFloor),
      maybe(seatId, getSeat),
      maybe(categoryId, getCategory),
    ]).then(([building, floor, seat, category]) => {
      if (cancelled) return
      const value = (result) => (result.status === 'fulfilled' ? result.value : null)
      setPlace({
        location: describeLocation(value(building), value(floor), value(seat)),
        category: value(category)?.name ?? null,
      })
    })
    return () => {
      cancelled = true
    }
  }, [buildingId, floorId, seatId, categoryId])

  useEffect(() => {
    if (!admin) return undefined
    let cancelled = false
    listUsers({ role: 'Engineer', is_active: true, limit: 100, sort: 'full_name', order: 'asc' })
      .then((page) => {
        if (!cancelled) setEngineers(page.items)
      })
      .catch(() => {
        if (!cancelled) setEngineers([])
      })
    return () => {
      cancelled = true
    }
  }, [admin])

  function afterMutation(message) {
    setNotice(message)
    reload()
  }

  if (loadError) {
    return result.status === 404 ? (
      <EmptyState
        icon={<MagnifyingGlass size={40} />}
        title="Incident not found"
        body="It may have been deleted, or it is not one you can see."
        action={
          <Button component={RouterLink} to="/" variant="outlined">
            Back to incidents
          </Button>
        }
      />
    ) : (
      <LoadError message={loadError} onRetry={reload} />
    )
  }
  if (!incident) return <PageSkeleton />

  const transitions = incident.allowed_transitions ?? []
  const escalations = data.escalations.value.items

  return (
    <Stack spacing={4} sx={{ opacity: loading ? 0.7 : 1 }} aria-busy={loading}>
      <Box>
        <Link
          component={RouterLink}
          to="/"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, mb: 2, textDecoration: 'none' }}
        >
          <ArrowLeft size={16} />
          Incidents
        </Link>
        <Typography component="h1" variant="h1" sx={{ overflowWrap: 'break-word' }}>
          {incident.title}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
          <StatusChip status={incident.status} />
          <PriorityChip priority={incident.priority} />
          <Typography variant="body2" color="text.secondary">
            Reported by {incident.reporter.full_name}{' '}
            <time dateTime={incident.created_at} title={formatDateTime(incident.created_at)}>
              {formatRelative(incident.created_at)}
            </time>
          </Typography>
        </Stack>
        {!wide && transitions.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <ActionsSection transitions={transitions} onPick={setPending} />
          </Box>
        )}
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 7fr) minmax(0, 5fr)' },
          gap: { xs: 4, md: 6 },
          alignItems: 'start',
        }}
      >
        <Stack spacing={5} sx={{ minWidth: 0 }}>
          <Box component="section" aria-labelledby="description-heading">
            <Typography id="description-heading" component="h2" variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
              Description
            </Typography>
            <Typography sx={{ whiteSpace: 'pre-wrap', maxWidth: '70ch' }}>{incident.description}</Typography>
            {incident.blocked_reason && incident.status === 'Blocked' && (
              <Typography sx={{ mt: 2, maxWidth: '70ch' }}>
                <Box component="span" sx={{ fontWeight: 500 }}>
                  Blocked:{' '}
                </Box>
                {incident.blocked_reason}
              </Typography>
            )}
            {incident.resolution_note && (
              <Typography sx={{ mt: 2, maxWidth: '70ch' }}>
                <Box component="span" sx={{ fontWeight: 500 }}>
                  Resolution:{' '}
                </Box>
                {incident.resolution_note}
              </Typography>
            )}
          </Box>

          <NotesSection
            incident={incident}
            notes={data.notes.value.items}
            error={data.notes.error}
            staff={staff}
            onAdd={async (note) => {
              await createNote(incident.id, note)
              afterMutation('Note added.')
            }}
            onRetry={reload}
          />

          <HistoryList history={data.history.value.items} error={data.history.error} onRetry={reload} />
        </Stack>

        <Stack
          spacing={4}
          sx={{
            minWidth: 0,
            position: { md: 'sticky' },
            top: { md: 88 },
            pl: { md: 4 },
            borderLeft: { md: 1 },
            borderColor: { md: 'divider' },
          }}
        >
          {wide && transitions.length > 0 && (
            <ActionsSection transitions={transitions} onPick={setPending} />
          )}

          {admin && (
            <TriagePanel
              key={`${incident.assignee_id}-${incident.priority}-${incident.status}`}
              incident={incident}
              engineers={engineers}
              onSave={async (changes) => {
                await updateIncident(incident.id, changes)
                afterMutation('Triage saved.')
              }}
            />
          )}

          <Box component="section" aria-labelledby="details-heading">
            <Typography id="details-heading" component="h2" variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
              Details
            </Typography>
            <Box component="dl" sx={{ m: 0, '& > div + div': { borderTop: 1, borderColor: 'divider' } }}>
              <Detail term="Assignee">
                {incident.assignee ? (
                  incident.assignee.full_name
                ) : (
                  <Box component="span" sx={{ color: 'text.secondary' }}>
                    Unassigned
                  </Box>
                )}
              </Detail>
              <Detail term="Location">
                {place.location || <Box component="span" sx={{ color: 'text.secondary' }}>Loading</Box>}
              </Detail>
              <Detail term="Category">
                {place.category ?? (
                  <Box component="span" sx={{ color: 'text.secondary' }}>
                    {incident.category_id ? 'Loading' : 'None'}
                  </Box>
                )}
              </Detail>
              <Detail term="Reported">
                <Stamp iso={incident.created_at} />
              </Detail>
              <Detail term="Acknowledged">
                <Stamp iso={incident.acknowledged_at} />
              </Detail>
              <Detail term="Resolved">
                <Stamp iso={incident.resolved_at} />
              </Detail>
              <Detail term="Closed">
                <Stamp iso={incident.closed_at} />
              </Detail>
            </Box>
          </Box>

          <EscalationPanel
            escalations={escalations}
            canRequest={canRequestEscalation(user, incident, escalations)}
            onRequest={async (reason) => {
              await requestEscalation(incident.id, reason)
              afterMutation('Escalation requested.')
            }}
          />
        </Stack>
      </Box>

      <TransitionDialog
        open={pending !== null}
        option={pending}
        incident={incident}
        user={user}
        engineers={engineers}
        onClose={() => setPending(null)}
        onSubmit={async (body) => {
          await transitionIncident(incident.id, body)
          setPending(null)
          afterMutation(`Now ${body.target_status}.`)
        }}
      />

      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

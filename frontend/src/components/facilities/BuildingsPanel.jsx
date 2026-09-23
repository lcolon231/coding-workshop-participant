import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import InputAdornment from '@mui/material/InputAdornment'
import OutlinedInput from '@mui/material/OutlinedInput'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { visuallyHidden } from '@mui/utils'
import { ArrowLeft, MagnifyingGlass } from '@phosphor-icons/react'
import ConfirmDialog from '../ConfirmDialog'
import RecordDialog from '../RecordDialog'
import RecordList from './RecordList'
import { useLoad } from '../../lib/useLoad'
import {
  createBuilding,
  createFloor,
  createSeat,
  deleteBuilding,
  deleteFloor,
  deleteSeat,
  listBuildings,
  listFloors,
  listSeats,
  updateBuilding,
  updateFloor,
  updateSeat,
} from '../../services/facilities'

const LEVELS = {
  building: {
    noun: 'building',
    fields: [
      {
        name: 'code',
        label: 'Code',
        required: true,
        maxLength: 20,
        readOnlyOnEdit: true,
        lockedHelp: 'Printed on signage, so it cannot be changed.',
        helperText: 'Short and unique, e.g. HQ.',
      },
      { name: 'name', label: 'Name', required: true, maxLength: 200 },
      { name: 'address', label: 'Address', maxLength: 400, multiline: true },
    ],
    create: createBuilding,
    update: updateBuilding,
    remove: deleteBuilding,
    retirable: true,
  },
  floor: {
    noun: 'floor',
    fields: [
      { name: 'level', label: 'Level', type: 'number', required: true, helperText: 'Basements are negative.' },
      { name: 'name', label: 'Name', maxLength: 100, helperText: 'Optional, e.g. Engineering.' },
    ],
    create: createFloor,
    update: updateFloor,
    remove: deleteFloor,
    retirable: false,
  },
  seat: {
    noun: 'seat',
    fields: [
      { name: 'code', label: 'Code', required: true, maxLength: 20, helperText: 'Unique on this floor, e.g. 2-03.' },
      { name: 'label', label: 'Label', maxLength: 100, helperText: 'Optional, e.g. Window desk.' },
    ],
    create: createSeat,
    update: updateSeat,
    remove: deleteSeat,
    retirable: true,
  },
}

function buildingTitle(building) {
  return `${building.code} · ${building.name}`
}

function floorTitle(floor) {
  return floor.name ? `Level ${floor.level} · ${floor.name}` : `Level ${floor.level}`
}

function seatTitle(seat) {
  return seat.label ? `${seat.code} · ${seat.label}` : seat.code
}

function matches(text, query) {
  return text.toLowerCase().includes(query.trim().toLowerCase())
}

/**
 * Buildings, their floors, and each floor's seats, side by side.
 *
 * Selection lives in the URL (`building`, `floor`) so a link opens the same
 * view. Above `md` the three columns sit together; below, one shows at a
 * time with a way back. Retired rows appear only with the page's "Show
 * retired" switch, which sets `include_inactive` on the API calls.
 */
export default function BuildingsPanel({ retired, notify }) {
  const wide = useMediaQuery((theme) => theme.breakpoints.up('md'))
  const [searchParams, setSearchParams] = useSearchParams()
  const buildingId = searchParams.get('building')
  const floorId = searchParams.get('floor')
  const [query, setQuery] = useState('')
  // `{ kind: 'create' | 'edit' | 'delete', level, record? }`
  const [dialog, setDialog] = useState(null)

  const loadBuildings = useCallback(() => listBuildings(retired ? { include_inactive: true } : {}), [retired])
  const loadFloors = useCallback(() => listFloors(buildingId), [buildingId])
  const loadSeats = useCallback(
    () => listSeats(floorId, retired ? { include_inactive: true } : {}),
    [floorId, retired],
  )
  const buildings = useLoad(loadBuildings)
  const floors = useLoad(loadFloors, Boolean(buildingId))
  const seats = useLoad(loadSeats, Boolean(floorId))
  const lists = { building: buildings, floor: floors, seat: seats }

  function select(changes) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setSearchParams(next)
  }

  const building = buildings.data?.items.find((item) => item.id === buildingId) ?? null
  const floor = floors.data?.items.find((item) => item.id === floorId) ?? null

  async function toggleRetired(level, record, title) {
    try {
      await LEVELS[level].update(record.id, { is_active: !record.is_active })
      notify(`${title} ${record.is_active ? 'retired' : 'restored'}.`)
      lists[level].reload()
    } catch (err) {
      notify(err.message)
    }
  }

  function rowActions(level, record, title) {
    const spec = LEVELS[level]
    const actions = [{ label: 'Edit', onClick: () => setDialog({ kind: 'edit', level, record }) }]
    if (spec.retirable) {
      actions.push({
        label: record.is_active ? 'Retire' : 'Restore',
        onClick: () => toggleRetired(level, record, title),
      })
    }
    actions.push({ label: 'Delete', destructive: true, onClick: () => setDialog({ kind: 'delete', level, record, title }) })
    return actions
  }

  const buildingRows =
    buildings.data === null
      ? null
      : buildings.data.items
          .filter((item) => !query || matches(`${item.code} ${item.name}`, query))
          .map((item) => ({
            id: item.id,
            primary: buildingTitle(item),
            secondary: item.address ?? 'No address',
            retired: !item.is_active,
            actions: rowActions('building', item, item.name),
          }))
  const floorRows =
    floors.data === null
      ? buildingId
        ? null
        : []
      : floors.data.items.map((item) => ({
          id: item.id,
          primary: floorTitle(item),
          secondary: undefined,
          actions: rowActions('floor', item, floorTitle(item)),
        }))
  const seatRows =
    seats.data === null
      ? floorId
        ? null
        : []
      : seats.data.items.map((item) => ({
          id: item.id,
          primary: seatTitle(item),
          secondary: undefined,
          retired: !item.is_active,
          actions: rowActions('seat', item, `Seat ${item.code}`),
        }))

  const buildingsColumn = (
    <RecordList
      title="Buildings"
      count={buildings.data?.total}
      addLabel="Add building"
      onAdd={() => setDialog({ kind: 'create', level: 'building' })}
      rows={buildingRows}
      loading={buildings.loading}
      error={buildings.error}
      onRetry={buildings.reload}
      selectedId={buildingId}
      onSelect={(id) => select({ building: id, floor: null })}
      emptyText={query ? 'No buildings match.' : 'No buildings yet.'}
      toolbar={
        <Box sx={{ mb: 1.5 }}>
          <Typography component="label" htmlFor="building-search" sx={visuallyHidden}>
            Search buildings
          </Typography>
          <OutlinedInput
            id="building-search"
            type="search"
            size="small"
            fullWidth
            placeholder="Search code or name"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            startAdornment={
              <InputAdornment position="start">
                <MagnifyingGlass size={16} />
              </InputAdornment>
            }
          />
        </Box>
      }
    />
  )
  const floorsColumn = (
    <RecordList
      title="Floors"
      count={floors.data?.total}
      addLabel="Add floor"
      onAdd={building ? () => setDialog({ kind: 'create', level: 'floor' }) : undefined}
      rows={floorRows}
      loading={floors.loading}
      error={floors.error}
      onRetry={floors.reload}
      selectedId={floorId}
      onSelect={(id) => select({ floor: id })}
      emptyText={buildingId ? 'No floors yet.' : 'Choose a building to see its floors.'}
      toolbar={
        building && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            In {building.name}
          </Typography>
        )
      }
    />
  )
  const seatsColumn = (
    <RecordList
      title="Seats"
      count={seats.data?.total}
      addLabel="Add seat"
      onAdd={floor ? () => setDialog({ kind: 'create', level: 'seat' }) : undefined}
      rows={seatRows}
      loading={seats.loading}
      error={seats.error}
      onRetry={seats.reload}
      emptyText={floorId ? 'No seats yet.' : 'Choose a floor to see its seats.'}
      toolbar={
        floor && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            On {floorTitle(floor).toLowerCase()}
            {building ? ` of ${building.name}` : ''}
          </Typography>
        )
      }
    />
  )

  let content
  if (wide) {
    content = (
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 3 }}>
        {buildingsColumn}
        {floorsColumn}
        {seatsColumn}
      </Box>
    )
  } else if (floorId) {
    content = (
      <Box>
        <Button startIcon={<ArrowLeft size={16} />} onClick={() => select({ floor: null })} sx={{ mb: 1 }}>
          Floors
        </Button>
        {seatsColumn}
      </Box>
    )
  } else if (buildingId) {
    content = (
      <Box>
        <Button startIcon={<ArrowLeft size={16} />} onClick={() => select({ building: null })} sx={{ mb: 1 }}>
          Buildings
        </Button>
        {floorsColumn}
      </Box>
    )
  } else {
    content = buildingsColumn
  }

  const spec = dialog ? LEVELS[dialog.level] : null
  const parentBody = dialog?.level === 'floor' ? { building_id: buildingId } : dialog?.level === 'seat' ? { floor_id: floorId } : {}

  return (
    <>
      {content}
      <RecordDialog
        open={dialog?.kind === 'create' || dialog?.kind === 'edit'}
        title={
          dialog?.kind === 'edit'
            ? `Edit ${spec.noun}`
            : dialog?.level === 'floor'
              ? `Add a floor to ${building?.name ?? 'this building'}`
              : dialog?.level === 'seat'
                ? `Add a seat on ${floor ? floorTitle(floor).toLowerCase() : 'this floor'}`
                : 'Add a building'
        }
        fields={spec?.fields ?? []}
        initial={dialog?.kind === 'edit' ? dialog.record : null}
        onClose={() => setDialog(null)}
        onSubmit={async (body) => {
          if (dialog.kind === 'create') {
            await spec.create({ ...parentBody, ...body })
            notify(`${spec.noun[0].toUpperCase()}${spec.noun.slice(1)} added.`)
          } else {
            await spec.update(dialog.record.id, body)
            notify(`${spec.noun[0].toUpperCase()}${spec.noun.slice(1)} saved.`)
          }
          lists[dialog.level].reload()
          setDialog(null)
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === 'delete'}
        title={dialog?.kind === 'delete' ? `Delete ${dialog.title}?` : ''}
        body={
          spec?.retirable
            ? `This only works while nothing refers to the ${spec?.noun}. If it is still in use the API will say so, and retiring it is the way to take it out of service.`
            : `This only works while nothing refers to the ${spec?.noun}. If it is still in use the API will say so.`
        }
        confirmLabel="Delete"
        destructive
        onClose={() => setDialog(null)}
        onConfirm={async () => {
          await spec.remove(dialog.record.id)
          notify(`${dialog.title} deleted.`)
          if (dialog.level === 'building' && dialog.record.id === buildingId) select({ building: null, floor: null })
          if (dialog.level === 'floor' && dialog.record.id === floorId) select({ floor: null })
          lists[dialog.level].reload()
          setDialog(null)
        }}
      />
    </>
  )
}

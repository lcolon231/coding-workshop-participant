import { useCallback, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
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
import { visuallyHidden } from '@mui/utils'
import { EmptyState, LoadError } from '../PageState'
import RecordDialog from '../RecordDialog'
import { useLoad } from '../../lib/useLoad'
import { listEngineers, updateEngineer } from '../../services/facilities'

const FIELDS = [
  { name: 'specialty', label: 'Specialty', required: true, maxLength: 100 },
  {
    name: 'max_concurrent_incidents',
    label: 'Maximum open assignments',
    type: 'number',
    required: true,
    min: 1,
    max: 50,
    helperText: 'How many non-closed incidents they can hold at once, from 1 to 50.',
  },
  { name: 'is_available', label: 'Available for new assignments', type: 'checkbox' },
]

const SORTS = [
  { value: 'full_name', label: 'Name' },
  { value: 'specialty', label: 'Specialty' },
  { value: 'open_assignments', label: 'Current load' },
]

function Filter({ id, label, value, onChange, children }) {
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
        sx={{ minWidth: { xs: '100%', sm: 180 }, '& .MuiSelect-select': { py: 1.25 } }}
      >
        {children}
      </Select>
    </Box>
  )
}

/**
 * Engineer profiles with their current load, so an admin can tune who
 * takes work. Profiles are created with the user (Users screen) and live
 * as long as the user, so this only edits.
 */
export default function EngineersPanel({ notify }) {
  const [sort, setSort] = useState('full_name')
  const [availability, setAvailability] = useState('')
  const load = useCallback(
    () =>
      listEngineers({
        sort,
        order: 'asc',
        is_available: availability === 'yes' ? true : availability === 'no' ? false : '',
      }),
    [sort, availability],
  )
  const { data, loading, error, reload } = useLoad(load)
  const [editing, setEditing] = useState(null)
  const items = data?.items ?? null

  return (
    <Box component="section" aria-labelledby="engineers-heading" aria-busy={loading}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        useFlexGap
        sx={{ alignItems: { sm: 'center' }, mb: 2, flexWrap: 'wrap' }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', flex: 1 }}>
          <Typography component="h2" variant="h6" id="engineers-heading" sx={{ fontWeight: 600 }}>
            Engineers
          </Typography>
          {data && (
            <Typography color="text.secondary" aria-label={`${data.total} in total`}>
              {data.total}
            </Typography>
          )}
        </Stack>
        <Filter id="engineer-availability" label="Availability" value={availability} onChange={setAvailability}>
          <option value="">Available and unavailable</option>
          <option value="yes">Available</option>
          <option value="no">Unavailable</option>
        </Filter>
        <Filter id="engineer-sort" label="Sort by" value={sort} onChange={setSort}>
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Filter>
      </Stack>
      {error && (
        <Box sx={{ mb: 1.5 }}>
          <LoadError message={error} onRetry={reload} />
        </Box>
      )}
      {items?.length === 0 ? (
        <EmptyState
          title="No engineers"
          body="Create a user with the Engineer role and they will appear here with their specialty and load."
        />
      ) : (
        <Table sx={{ opacity: loading && items ? 0.6 : 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>Engineer</TableCell>
              <TableCell>Specialty</TableCell>
              <TableCell>Availability</TableCell>
              <TableCell>Load</TableCell>
              <TableCell align="right">
                <Box component="span" sx={visuallyHidden}>
                  Actions
                </Box>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items === null
              ? Array.from({ length: 3 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton width="60%" />
                    </TableCell>
                    <TableCell>
                      <Skeleton width={90} />
                    </TableCell>
                    <TableCell>
                      <Skeleton width={80} />
                    </TableCell>
                    <TableCell>
                      <Skeleton width={50} />
                    </TableCell>
                    <TableCell />
                  </TableRow>
                ))
              : items.map((engineer) => (
                  <TableRow key={engineer.user_id} hover>
                    <TableCell sx={{ fontWeight: 500 }}>{engineer.user.full_name}</TableCell>
                    <TableCell>{engineer.specialty}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={engineer.is_available ? 'Available' : 'Unavailable'}
                        color={engineer.is_available ? 'success' : 'default'}
                        sx={{ fontWeight: 500 }}
                      />
                    </TableCell>
                    <TableCell
                      sx={{
                        color: engineer.open_assignments >= engineer.max_concurrent_incidents ? 'warning.main' : 'text.primary',
                      }}
                    >
                      {engineer.open_assignments} of {engineer.max_concurrent_incidents}
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" variant="outlined" sx={{ minHeight: 32 }} onClick={() => setEditing(engineer)}>
                        Edit
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      )}

      <RecordDialog
        open={editing !== null}
        title={editing ? `Edit ${editing.user.full_name}` : ''}
        fields={FIELDS}
        initial={editing}
        onClose={() => setEditing(null)}
        onSubmit={async (body) => {
          await updateEngineer(editing.user_id, body)
          notify(`${editing.user.full_name} saved.`)
          reload()
          setEditing(null)
        }}
      />
    </Box>
  )
}

import { useEffect, useState } from 'react'
import { usePageTitle } from '../lib/usePageTitle'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Field from '../components/Field'
import SelectField from '../components/SelectField'
import { focusFirstError, splitDetails } from '../lib/formErrors'
import { PRIORITIES } from '../lib/incidents'
import { ApiError } from '../services/api'
import { listBuildings, listCategories, listFloors, listSeats } from '../services/facilities'
import { createIncident } from '../services/incidents'

const FIELDS = ['title', 'description', 'priority', 'category_id', 'building_id', 'floor_id', 'seat_id']
const TITLE_MAX = 200

const SECTION_HEADING = {
  fontSize: '0.8125rem',
  fontWeight: 600,
  letterSpacing: '0.04em',
  textTransform: 'uppercase',
  color: 'text.secondary',
}

const EMPTY = {
  title: '',
  description: '',
  priority: 'Medium',
  category_id: '',
  building_id: '',
  floor_id: '',
  seat_id: '',
}

function validate(values) {
  const errors = {}
  if (!values.title.trim()) errors.title = 'Give the incident a short title.'
  else if (values.title.trim().length > TITLE_MAX) errors.title = `Keep the title under ${TITLE_MAX} characters.`
  if (!values.description.trim()) errors.description = 'Describe what is wrong and where.'
  if (!values.building_id) errors.building_id = 'Choose the building.'
  return errors
}

function floorLabel(floor) {
  return floor.name ? `${floor.name} (level ${floor.level})` : `Level ${floor.level}`
}

function seatLabel(seat) {
  return seat.label ? `${seat.code}, ${seat.label}` : seat.code
}

/** Group a flat category list into roots and their children, for `<optgroup>`s. */
function groupCategories(items) {
  const roots = items.filter((item) => item.parent_id === null)
  return roots.map((root) => ({
    root,
    children: items.filter((item) => item.parent_id === root.id),
  }))
}

/**
 * A list that loads once its parameter is known and forgets itself when the
 * parameter changes, so the floor list never shows another building's floors.
 */
function useOptions(loader, key) {
  const [result, setResult] = useState({ key: null, items: [], error: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (key === null) return undefined
    let cancelled = false
    loader(key)
      .then((page) => {
        if (!cancelled) setResult({ key, items: page.items, error: null })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, items: [], error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [loader, key, attempt])
  // `null` items means "still loading"; a parameter of null means "nothing to load".
  const current = key === null ? { items: [], error: null } : result.key === key ? result : { items: null, error: null }
  return { ...current, retry: () => setAttempt((n) => n + 1) }
}

const loadBuildings = () => listBuildings()
const loadCategories = () => listCategories()

export default function NewIncidentPage() {
  usePageTitle('Report an incident')
  const navigate = useNavigate()
  const [values, setValues] = useState(EMPTY)
  const [fieldErrors, setFieldErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const buildings = useOptions(loadBuildings, 'all')
  const categories = useOptions(loadCategories, 'all')
  const floors = useOptions(listFloors, values.building_id || null)
  const seats = useOptions(listSeats, values.floor_id || null)

  function handleChange(event) {
    const { name, value } = event.target
    setValues((current) => {
      const next = { ...current, [name]: value }
      // The cascade: a new building forgets the floor and seat, a new floor forgets the seat.
      if (name === 'building_id') Object.assign(next, { floor_id: '', seat_id: '' })
      if (name === 'floor_id') next.seat_id = ''
      return next
    })
    setFieldErrors((current) => (current[name] ? { ...current, [name]: undefined } : current))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const clientErrors = validate(values)
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors)
      focusFirstError(clientErrors, FIELDS)
      return
    }

    setSubmitting(true)
    setFormError(null)
    try {
      await createIncident({
        title: values.title.trim(),
        description: values.description.trim(),
        priority: values.priority,
        category_id: values.category_id || null,
        building_id: values.building_id,
        floor_id: values.floor_id || null,
        seat_id: values.seat_id || null,
      })
      // Back to the list rather than the new incident's page: an engineer
      // cannot see their own report until an admin assigns it, so the
      // detail page would 404 on them.
      navigate('/', { replace: true, state: { notice: 'Incident created successfully.' } })
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const { fieldErrors: serverErrors, formErrors } = splitDetails(err.details, FIELDS)
        setFieldErrors(serverErrors)
        focusFirstError(serverErrors, FIELDS)
        const hasInline = Object.keys(serverErrors).length > 0
        setFormError(formErrors.length > 0 ? formErrors.join(' ') : hasInline ? null : err.message)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const buildingHelp = buildings.error
    ? null
    : buildings.items?.length === 0
      ? 'No buildings have been set up yet. Ask a facility admin.'
      : undefined

  return (
    <Box sx={{ maxWidth: 1040 }}>
      <Typography component="h1" variant="h1" sx={{ mb: 0.5 }}>
        Report an incident
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2.5 }}>
        Say what is wrong and where it is. A facility admin will assign an engineer.
      </Typography>

      <Stack component="form" noValidate onSubmit={handleSubmit} aria-busy={submitting} spacing={2.5}>
        {formError && <Alert severity="error">{formError}</Alert>}

        {/*
          Two columns on a desktop so the whole form sits above the fold: what
          happened on the left, where it is on the right. One column on a
          phone, in the same reading order.
        */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(0, 3fr) minmax(0, 2fr)' },
            columnGap: 6,
            rowGap: 2.5,
            alignItems: 'start',
          }}
        >
          <Stack component="section" aria-labelledby="what-heading" spacing={2.5}>
            <Typography id="what-heading" component="h2" sx={SECTION_HEADING}>
              What happened
            </Typography>
            <Field
              id="title"
              label="Title"
              autoFocus
              value={values.title}
              onChange={handleChange}
              error={fieldErrors.title}
              helperText="One line, like a subject: what and where."
              inputAttributes={{ maxLength: TITLE_MAX }}
            />
            <Field
              id="description"
              label="Description"
              multiline
              minRows={4}
              value={values.description}
              onChange={handleChange}
              error={fieldErrors.description}
              helperText="What you noticed, since when, and anything that helps find it."
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
              <SelectField
                id="priority"
                label="Priority"
                value={values.priority}
                onChange={handleChange}
                error={fieldErrors.priority}
                helperText="Admins can adjust it later."
              >
                {PRIORITIES.map((priority) => (
                  <option key={priority} value={priority}>
                    {priority}
                  </option>
                ))}
              </SelectField>
              <SelectField
                id="category_id"
                label="Category"
                value={values.category_id}
                onChange={handleChange}
                error={fieldErrors.category_id}
                disabled={categories.items === null || Boolean(categories.error)}
                helperText={categories.error ? 'Categories could not be loaded; you can leave this blank.' : 'Optional.'}
              >
                <option value="">Not sure</option>
                {groupCategories(categories.items ?? []).map(({ root, children }) =>
                  children.length === 0 ? (
                    <option key={root.id} value={root.id}>
                      {root.name}
                    </option>
                  ) : (
                    <optgroup key={root.id} label={root.name}>
                      <option value={root.id}>{root.name}</option>
                      {children.map((child) => (
                        <option key={child.id} value={child.id}>
                          {child.name}
                        </option>
                      ))}
                    </optgroup>
                  ),
                )}
              </SelectField>
            </Box>
          </Stack>

          <Stack component="section" aria-labelledby="where-heading" spacing={2.5}>
            <Typography id="where-heading" component="h2" sx={SECTION_HEADING}>
              Where it is
            </Typography>
            {buildings.error && (
              <Alert
                severity="error"
                action={
                  <Button color="inherit" size="small" onClick={buildings.retry}>
                    Try again
                  </Button>
                }
              >
                Buildings could not be loaded. {buildings.error}
              </Alert>
            )}
            <SelectField
              id="building_id"
              label="Building"
              value={values.building_id}
              onChange={handleChange}
              error={fieldErrors.building_id}
              disabled={buildings.items === null || Boolean(buildings.error)}
              helperText={buildingHelp}
            >
              <option value="">{buildings.items === null ? 'Loading buildings' : 'Choose a building'}</option>
              {(buildings.items ?? []).map((building) => (
                <option key={building.id} value={building.id}>
                  {building.code}, {building.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              id="floor_id"
              label="Floor"
              value={values.floor_id}
              onChange={handleChange}
              error={fieldErrors.floor_id}
              disabled={!values.building_id || floors.items === null}
              helperText={
                floors.error
                  ? 'Floors could not be loaded; you can leave this blank.'
                  : 'Optional. A lift or a lobby has no floor.'
              }
            >
              <option value="">{!values.building_id ? 'Choose a building first' : 'Any floor'}</option>
              {(floors.items ?? []).map((floor) => (
                <option key={floor.id} value={floor.id}>
                  {floorLabel(floor)}
                </option>
              ))}
            </SelectField>
            <SelectField
              id="seat_id"
              label="Seat"
              value={values.seat_id}
              onChange={handleChange}
              error={fieldErrors.seat_id}
              disabled={!values.floor_id || seats.items === null}
              helperText={
                seats.error ? 'Seats could not be loaded; you can leave this blank.' : 'Optional.'
              }
            >
              <option value="">{!values.floor_id ? 'Choose a floor first' : 'Any seat'}</option>
              {(seats.items ?? []).map((seat) => (
                <option key={seat.id} value={seat.id}>
                  {seatLabel(seat)}
                </option>
              ))}
            </SelectField>
          </Stack>
        </Box>

        <Stack direction="row" spacing={1.5} sx={{ pt: 0.5 }}>
          <Button type="submit" variant="contained" size="large" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit report'}
          </Button>
          <Button component={RouterLink} to="/" variant="text" size="large" disabled={submitting}>
            Cancel
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}

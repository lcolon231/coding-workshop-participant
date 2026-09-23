import { useState } from 'react'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import SelectField from '../SelectField'
import { PRIORITIES } from '../../lib/incidents'
import { ApiError } from '../../services/api'

/**
 * Admin only: set the assignee and the priority through `PUT`.
 *
 * Unassigning is offered only while the incident is Open, because In Progress
 * requires an assignee and the API would refuse.
 */
export default function TriagePanel({ incident, engineers, onSave }) {
  const [assignee, setAssignee] = useState(incident.assignee_id ?? '')
  const [priority, setPriority] = useState(incident.priority)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const closed = incident.status === 'Closed'
  const changed = assignee !== (incident.assignee_id ?? '') || priority !== incident.priority
  const canUnassign = incident.status === 'Open'

  async function handleSubmit(event) {
    event.preventDefault()
    const changes = {}
    if (assignee !== (incident.assignee_id ?? '')) changes.assignee_id = assignee || null
    if (priority !== incident.priority) changes.priority = priority
    setSaving(true)
    setError(null)
    try {
      await onSave(changes)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Stack
      component="form"
      noValidate
      onSubmit={handleSubmit}
      spacing={2}
      aria-busy={saving}
      aria-labelledby="triage-heading"
    >
      <Typography id="triage-heading" component="h2" variant="h6" sx={{ fontWeight: 600 }}>
        Triage
      </Typography>
      {closed ? (
        <Typography color="text.secondary">A closed incident can no longer be changed.</Typography>
      ) : (
        <>
          {error && <Alert severity="error">{error}</Alert>}
          <SelectField
            id="triage-assignee"
            name="assignee_id"
            label="Assignee"
            value={assignee}
            onChange={(event) => setAssignee(event.target.value)}
            disabled={engineers === null}
            helperText={
              !canUnassign && incident.assignee_id
                ? 'An incident in progress always has an engineer.'
                : undefined
            }
          >
            {(canUnassign || !incident.assignee_id) && (
              <option value="">{engineers === null ? 'Loading engineers' : 'Unassigned'}</option>
            )}
            {(engineers ?? []).map((engineer) => (
              <option key={engineer.id} value={engineer.id}>
                {engineer.full_name}
              </option>
            ))}
          </SelectField>
          <SelectField
            id="triage-priority"
            name="priority"
            label="Priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
          >
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </SelectField>
          <Button type="submit" variant="outlined" disabled={!changed || saving} sx={{ alignSelf: 'flex-start' }}>
            {saving ? 'Saving…' : 'Save triage'}
          </Button>
        </>
      )}
    </Stack>
  )
}

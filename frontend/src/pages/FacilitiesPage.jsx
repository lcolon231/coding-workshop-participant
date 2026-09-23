import { useState } from 'react'
import { usePageTitle } from '../lib/usePageTitle'
import { useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import BuildingsPanel from '../components/facilities/BuildingsPanel'
import CategoriesPanel from '../components/facilities/CategoriesPanel'
import EngineersPanel from '../components/facilities/EngineersPanel'
import Notice from '../components/Notice'

const TABS = [
  { value: 'buildings', label: 'Buildings' },
  { value: 'categories', label: 'Categories' },
  { value: 'engineers', label: 'Engineers' },
]

/**
 * Everything an incident is filed against: where (buildings, floors,
 * seats), what (categories) and who fixes it (engineer profiles).
 *
 * The tab and the "Show retired" switch live in the URL alongside the
 * panels' own selection, so the whole view is linkable.
 */
export default function FacilitiesPage() {
  usePageTitle('Facilities')
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = TABS.some((item) => item.value === searchParams.get('tab')) ? searchParams.get('tab') : 'buildings'
  const retired = searchParams.get('retired') === '1'
  const [notice, setNotice] = useState(null)

  function setParam(key, value) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next)
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography component="h1" variant="h1">
          Facilities
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          Where incidents happen, how they are categorised, and who fixes them.
        </Typography>
      </Box>

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', borderBottom: 1, borderColor: 'divider' }}
      >
        <Tabs value={tab} onChange={(_, value) => setParam('tab', value === 'buildings' ? null : value)} aria-label="Facility sections">
          {TABS.map((item) => (
            <Tab key={item.value} value={item.value} label={item.label} sx={{ fontWeight: 600, minHeight: 48 }} />
          ))}
        </Tabs>
        {tab !== 'engineers' && (
          <FormControlLabel
            control={<Switch checked={retired} onChange={(event) => setParam('retired', event.target.checked ? '1' : null)} />}
            label="Show retired"
            sx={{ mr: 0, pb: { xs: 1, sm: 0 } }}
          />
        )}
      </Stack>

      {tab === 'buildings' && <BuildingsPanel retired={retired} notify={setNotice} />}
      {tab === 'categories' && <CategoriesPanel retired={retired} notify={setNotice} />}
      {tab === 'engineers' && <EngineersPanel notify={setNotice} />}

      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

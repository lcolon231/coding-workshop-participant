import { useCallback, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Plus } from '@phosphor-icons/react'
import ConfirmDialog from '../ConfirmDialog'
import { EmptyState, LoadError } from '../PageState'
import RecordDialog from '../RecordDialog'
import { RetiredChip, RowMenu } from './RecordList'
import { useLoad } from '../../lib/useLoad'
import { createCategory, deleteCategory, listCategories, updateCategory } from '../../services/facilities'

const FIELDS = [
  { name: 'name', label: 'Name', required: true, maxLength: 100 },
  { name: 'description', label: 'Description', maxLength: 400, multiline: true, helperText: 'Optional. Shown to reporters choosing a category.' },
]

/** The flat list as roots with their children, both alphabetical. */
function toTree(items) {
  const byName = (a, b) => a.name.localeCompare(b.name)
  const roots = items.filter((item) => item.parent_id === null).sort(byName)
  return roots.map((root) => ({
    ...root,
    children: items.filter((item) => item.parent_id === root.id).sort(byName),
  }))
}

/**
 * The two-level category tree: roots as sections, children beneath.
 *
 * The API returns a flat list and refuses re-parenting, so a child is
 * created under its root and stays there. Retired categories show only
 * with the page's "Show retired" switch.
 */
export default function CategoriesPanel({ retired, notify }) {
  const load = useCallback(() => listCategories(retired ? { include_inactive: true } : {}), [retired])
  const { data, loading, error, reload } = useLoad(load)
  // `{ kind: 'create' | 'edit' | 'delete', record?, parent? }`
  const [dialog, setDialog] = useState(null)
  const tree = data ? toTree(data.items) : null

  async function toggleRetired(record) {
    try {
      await updateCategory(record.id, { is_active: !record.is_active })
      notify(`${record.name} ${record.is_active ? 'retired' : 'restored'}.`)
      reload()
    } catch (err) {
      notify({ message: err.message, severity: 'error' })
    }
  }

  function actionsFor(record, { root }) {
    const actions = []
    if (root) actions.push({ label: 'Add sub-category', onClick: () => setDialog({ kind: 'create', parent: record }) })
    actions.push(
      { label: 'Edit', onClick: () => setDialog({ kind: 'edit', record }) },
      { label: record.is_active ? 'Retire' : 'Restore', onClick: () => toggleRetired(record) },
      { label: 'Delete', destructive: true, onClick: () => setDialog({ kind: 'delete', record }) },
    )
    return actions
  }

  function row(record, { root }) {
    return (
      <ListItem
        key={record.id}
        sx={{ pl: root ? 2 : 5, pr: 7, py: root ? 1.25 : 0.75 }}
        secondaryAction={<RowMenu name={record.name} actions={actionsFor(record, { root })} />}
      >
        <ListItemText
          primary={
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Box component="span" sx={{ fontWeight: root ? 600 : 500 }}>
                {record.name}
              </Box>
              {!record.is_active && <RetiredChip />}
            </Stack>
          }
          secondary={record.description ?? undefined}
        />
      </ListItem>
    )
  }

  return (
    <Box component="section" aria-labelledby="categories-heading" aria-busy={loading}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', flex: 1 }}>
          <Typography component="h2" variant="h6" id="categories-heading" sx={{ fontWeight: 600 }}>
            Categories
          </Typography>
          {data && (
            <Typography color="text.secondary" aria-label={`${data.total} in total`}>
              {data.total}
            </Typography>
          )}
        </Stack>
        <Button
          size="small"
          variant="outlined"
          startIcon={<Plus size={14} weight="bold" />}
          onClick={() => setDialog({ kind: 'create', parent: null })}
          sx={{ minHeight: 32 }}
        >
          Add category
        </Button>
      </Stack>
      {error && (
        <Box sx={{ mb: 1.5 }}>
          <LoadError message={error} onRetry={reload} />
        </Box>
      )}
      {tree?.length === 0 ? (
        <EmptyState
          title="No categories yet"
          body="Add a top-level category such as Facilities, then sub-categories such as HVAC beneath it."
        />
      ) : (
        <List
          disablePadding
          sx={{ border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', opacity: loading && tree ? 0.6 : 1 }}
        >
          {tree === null &&
            Array.from({ length: 3 }, (_, i) => (
              <ListItem key={i}>
                <ListItemText primary={<Skeleton width="40%" />} />
              </ListItem>
            ))}
          {tree?.map((root, index) => (
            <Box
              key={root.id}
              component="li"
              sx={{ listStyle: 'none', borderTop: index > 0 ? 1 : 0, borderColor: 'divider' }}
            >
              <List disablePadding aria-label={root.name}>
                {row(root, { root: true })}
                {root.children.map((child) => row(child, { root: false }))}
              </List>
            </Box>
          ))}
        </List>
      )}

      <RecordDialog
        open={dialog?.kind === 'create' || dialog?.kind === 'edit'}
        title={
          dialog?.kind === 'edit'
            ? `Edit ${dialog.record.name}`
            : dialog?.parent
              ? `Add a sub-category under ${dialog.parent.name}`
              : 'Add a category'
        }
        description={dialog?.kind === 'create' && !dialog.parent ? 'A top-level category. Sub-categories are added from its menu.' : undefined}
        fields={FIELDS}
        initial={dialog?.kind === 'edit' ? dialog.record : null}
        onClose={() => setDialog(null)}
        onSubmit={async (body) => {
          if (dialog.kind === 'create') {
            await createCategory(dialog.parent ? { parent_id: dialog.parent.id, ...body } : body)
            notify('Category added.')
          } else {
            await updateCategory(dialog.record.id, body)
            notify('Category saved.')
          }
          reload()
          setDialog(null)
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === 'delete'}
        title={dialog?.kind === 'delete' ? `Delete ${dialog.record.name}?` : ''}
        body="This only works while no sub-category or incident refers to it. If it is still in use the API will say so, and retiring it is the way to take it out of service."
        confirmLabel="Delete"
        destructive
        onClose={() => setDialog(null)}
        onConfirm={async () => {
          await deleteCategory(dialog.record.id)
          notify(`${dialog.record.name} deleted.`)
          reload()
          setDialog(null)
        }}
      />
    </Box>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import InputAdornment from '@mui/material/InputAdornment'
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
import useMediaQuery from '@mui/material/useMediaQuery'
import { visuallyHidden } from '@mui/utils'
import { MagnifyingGlass, Plus, UsersThree } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthContext'
import UserDialog from '../components/admin/UserDialog'
import ConfirmDialog from '../components/ConfirmDialog'
import { EmptyState, LoadError } from '../components/PageState'
import Notice from '../components/Notice'
import { formatDate } from '../lib/format'
import { PAGE_SIZE } from '../lib/incidents'
import { ROLES, USER_SORT_OPTIONS } from '../lib/users'
import { createUser, deactivateUser, listUsers, updateUser } from '../services/auth'

const DEFAULT_SORT = USER_SORT_OPTIONS[0].value

function readFilters(params) {
  const page = Number.parseInt(params.get('page') ?? '1', 10)
  return {
    role: params.get('role') ?? '',
    active: params.get('active') ?? '',
    search: params.get('search') ?? '',
    sort: params.get('sort') ?? DEFAULT_SORT,
    page: Number.isFinite(page) && page > 0 ? page : 1,
  }
}

function hasFilters(filters) {
  return Boolean(filters.role || filters.active || filters.search)
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

function ActiveChip({ active }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={active ? 'Active' : 'Inactive'}
      color={active ? 'success' : 'default'}
      sx={{ fontWeight: 500 }}
    />
  )
}

/** Edit, and deactivate or reactivate. The signed-in admin cannot deactivate themselves. */
function RowActions({ user, self, onEdit, onDeactivate, onReactivate }) {
  return (
    <Stack direction="row" spacing={1} sx={{ justifyContent: { md: 'flex-end' } }}>
      <Button size="small" variant="outlined" sx={{ minHeight: 32 }} onClick={() => onEdit(user)}>
        Edit
      </Button>
      {user.is_active ? (
        <Button
          size="small"
          color="error"
          sx={{ minHeight: 32 }}
          disabled={self}
          title={self ? 'You cannot deactivate your own account.' : undefined}
          onClick={() => onDeactivate(user)}
        >
          Deactivate
        </Button>
      ) : (
        <Button size="small" sx={{ minHeight: 32 }} onClick={() => onReactivate(user)}>
          Reactivate
        </Button>
      )}
    </Stack>
  )
}

function RowSkeleton() {
  return (
    <TableRow>
      <TableCell>
        <Skeleton width="60%" />
        <Skeleton width="40%" />
      </TableCell>
      <TableCell>
        <Skeleton width={80} />
      </TableCell>
      <TableCell>
        <Skeleton width={100} />
      </TableCell>
      <TableCell>
        <Skeleton width={56} />
      </TableCell>
      <TableCell>
        <Skeleton width={90} />
      </TableCell>
      <TableCell />
    </TableRow>
  )
}

function UserTable({ items, loading, selfId, actions }) {
  return (
    <Table aria-busy={loading} sx={{ opacity: loading ? 0.6 : 1 }}>
      <TableHead>
        <TableRow>
          <TableCell>Name</TableCell>
          <TableCell>Role</TableCell>
          <TableCell>Occupation</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Joined</TableCell>
          <TableCell align="right">
            <Box component="span" sx={visuallyHidden}>
              Actions
            </Box>
          </TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items === null
          ? Array.from({ length: 6 }, (_, i) => <RowSkeleton key={i} />)
          : items.map((user) => (
              <TableRow key={user.id} hover>
                <TableCell sx={{ maxWidth: 360 }}>
                  <Typography sx={{ fontWeight: 500 }}>
                    {user.full_name}
                    {user.id === selfId && (
                      <Typography component="span" variant="body2" color="text.secondary">
                        {' '}
                        (you)
                      </Typography>
                    )}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    {user.email}
                  </Typography>
                </TableCell>
                <TableCell>{user.role}</TableCell>
                <TableCell sx={{ color: user.occupation ? 'text.primary' : 'text.secondary' }}>
                  {user.occupation ?? '—'}
                </TableCell>
                <TableCell>
                  <ActiveChip active={user.is_active} />
                </TableCell>
                <TableCell>
                  <time dateTime={user.created_at}>{formatDate(user.created_at)}</time>
                </TableCell>
                <TableCell align="right">
                  <RowActions user={user} self={user.id === selfId} {...actions} />
                </TableCell>
              </TableRow>
            ))}
      </TableBody>
    </Table>
  )
}

/** Below `md` the table becomes a stack of rows. */
function UserCards({ items, loading, selfId, actions }) {
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
        : items.map((user) => (
            <Box component="li" key={user.id} sx={{ py: 2, borderBottom: 1, borderColor: 'divider' }}>
              <Typography sx={{ fontWeight: 500 }}>
                {user.full_name}
                {user.id === selfId && ' (you)'}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {user.email}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mb: 1.5, alignItems: 'center' }}>
                <Chip size="small" variant="outlined" label={user.role} sx={{ fontWeight: 500 }} />
                <ActiveChip active={user.is_active} />
              </Stack>
              <RowActions user={user} self={user.id === selfId} {...actions} />
            </Box>
          ))}
    </Stack>
  )
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const wide = useMediaQuery((theme) => theme.breakpoints.up('md'))
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => readFilters(searchParams), [searchParams])
  const [draft, setDraft] = useState({ base: filters.search, text: filters.search })
  const searchText = draft.base === filters.search ? draft.text : filters.search
  const setSearchText = (text) => setDraft({ base: filters.search, text })
  const [attempt, setAttempt] = useState(0)
  const key = `${searchParams.toString()}#${attempt}`
  const [result, setResult] = useState({ key: null, page: null, error: null })
  // `dialog` is `{ kind: 'create' } | { kind: 'edit', user } | { kind: 'deactivate', user }`.
  const [dialog, setDialog] = useState(null)
  const [notice, setNotice] = useState(null)

  const update = useCallback(
    (changes) => {
      const next = new URLSearchParams(searchParams)
      for (const [key, value] of Object.entries({ page: '1', ...changes })) {
        if (value === '' || value === null || (key === 'page' && value === '1')) next.delete(key)
        else next.set(key, String(value))
      }
      setSearchParams(next)
    },
    [searchParams, setSearchParams],
  )

  useEffect(() => {
    if (searchText === filters.search) return undefined
    const timer = setTimeout(() => update({ search: searchText.trim() }), 300)
    return () => clearTimeout(timer)
  }, [searchText, filters.search, update])

  useEffect(() => {
    let cancelled = false
    const [sort, order] = filters.sort.split(':')
    listUsers({
      role: filters.role,
      is_active: filters.active === 'active' ? true : filters.active === 'inactive' ? false : '',
      search: filters.search,
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
  }, [filters, key])

  const reload = () => setAttempt((n) => n + 1)
  function afterMutation(message) {
    setDialog(null)
    setNotice(message)
    reload()
  }

  const loading = result.key !== key
  const { page } = result
  const error = loading ? null : result.error
  const items = page?.items ?? null
  const pageCount = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1
  const first = page ? page.offset + 1 : 0
  const last = page ? page.offset + page.items.length : 0

  const actions = {
    onEdit: (user) => setDialog({ kind: 'edit', user }),
    onDeactivate: (user) => setDialog({ kind: 'deactivate', user }),
    onReactivate: async (user) => {
      try {
        await updateUser(user.id, { is_active: true })
        afterMutation(`${user.full_name} reactivated.`)
      } catch (err) {
        setNotice({ message: err.message, severity: 'error' })
      }
    },
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography component="h1" variant="h1">
            Users
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            Everyone who can sign in, and what they may do.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={16} weight="bold" />}
          onClick={() => setDialog({ kind: 'create' })}
          sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
        >
          New user
        </Button>
      </Stack>

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
            Search users
          </Typography>
          <OutlinedInput
            id="search"
            type="search"
            fullWidth
            size="small"
            placeholder="Search name or email"
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
        <FilterSelect id="filter-role" label="Role" value={filters.role} onChange={(v) => update({ role: v })}>
          <option value="">Any role</option>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </FilterSelect>
        <FilterSelect id="filter-active" label="Status" value={filters.active} onChange={(v) => update({ active: v })}>
          <option value="">Active and inactive</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </FilterSelect>
        <FilterSelect id="filter-sort" label="Sort by" value={filters.sort} onChange={(v) => update({ sort: v, page: String(filters.page) })}>
          {USER_SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </FilterSelect>
      </Stack>

      {error && <LoadError message={error} onRetry={reload} />}

      {items?.length === 0 ? (
        <EmptyState
          icon={<UsersThree size={40} />}
          title={hasFilters(filters) ? 'No users match' : 'No users yet'}
          body={hasFilters(filters) ? 'Try a different role, status or search.' : 'Create the first account.'}
          action={
            hasFilters(filters) ? (
              <Button variant="outlined" onClick={() => setSearchParams({})}>
                Clear filters
              </Button>
            ) : (
              <Button variant="contained" onClick={() => setDialog({ kind: 'create' })}>
                New user
              </Button>
            )
          }
        />
      ) : (
        <Box>
          {wide ? (
            <UserTable items={items} loading={loading} selfId={me.id} actions={actions} />
          ) : (
            <UserCards items={items} loading={loading} selfId={me.id} actions={actions} />
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

      <UserDialog
        open={dialog?.kind === 'create' || dialog?.kind === 'edit'}
        user={dialog?.kind === 'edit' ? dialog.user : null}
        self={dialog?.kind === 'edit' && dialog.user.id === me.id}
        onClose={() => setDialog(null)}
        onSubmit={async (body) => {
          if (dialog.kind === 'create') {
            const created = await createUser(body)
            afterMutation(`${created.full_name} created as ${created.role}.`)
          } else {
            const updated = await updateUser(dialog.user.id, body)
            afterMutation(`${updated.full_name} saved.`)
          }
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === 'deactivate'}
        title={dialog?.kind === 'deactivate' ? `Deactivate ${dialog.user.full_name}?` : ''}
        body="They are signed out everywhere and can no longer sign in. Their incidents are kept, and the account can be reactivated later."
        confirmLabel="Deactivate"
        destructive
        onClose={() => setDialog(null)}
        onConfirm={async () => {
          await deactivateUser(dialog.user.id)
          afterMutation(`${dialog.user.full_name} deactivated.`)
        }}
      />
      <Notice notice={notice} onClose={() => setNotice(null)} />
    </Stack>
  )
}

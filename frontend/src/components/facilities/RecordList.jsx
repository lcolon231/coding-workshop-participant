import { useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { DotsThree, Plus } from '@phosphor-icons/react'
import { LoadError } from '../PageState'

/** The per-row actions, behind one button so a narrow column stays readable. */
export function RowMenu({ name, actions }) {
  const [anchor, setAnchor] = useState(null)
  const open = Boolean(anchor)
  return (
    <>
      <IconButton
        size="small"
        aria-label={`Actions for ${name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation()
          setAnchor(event.currentTarget)
        }}
      >
        <DotsThree size={20} weight="bold" />
      </IconButton>
      <Menu anchorEl={anchor} open={open} onClose={() => setAnchor(null)}>
        {actions.map((action) => (
          <MenuItem
            key={action.label}
            onClick={() => {
              setAnchor(null)
              action.onClick()
            }}
            sx={action.destructive ? { color: 'error.main' } : undefined}
          >
            {action.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  )
}

export function RetiredChip() {
  return <Chip size="small" variant="outlined" label="Retired" sx={{ fontWeight: 500 }} />
}

/**
 * One column of records: a heading, an add button, then rows that can be
 * selected (to drill into their children) and acted on.
 *
 * `rows` is `{ id, primary, secondary, retired, actions }`. `null` rows means
 * still loading; `[]` means empty, explained by `emptyText`.
 */
export default function RecordList({
  title,
  count,
  addLabel,
  onAdd,
  rows,
  loading,
  error,
  onRetry,
  selectedId,
  onSelect,
  emptyText,
  toolbar,
  headingLevel = 'h2',
}) {
  const headingId = `${title.toLowerCase().replace(/\s+/g, '-')}-heading`
  return (
    <Box component="section" aria-labelledby={headingId} aria-busy={loading} sx={{ minWidth: 0 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', flex: 1, minWidth: 0 }}>
          <Typography component={headingLevel} variant="h6" id={headingId} sx={{ fontWeight: 600 }}>
            {title}
          </Typography>
          {typeof count === 'number' && (
            <Typography color="text.secondary" aria-label={`${count} in total`}>
              {count}
            </Typography>
          )}
        </Stack>
        {onAdd && (
          <Button size="small" variant="outlined" startIcon={<Plus size={14} weight="bold" />} onClick={onAdd} sx={{ minHeight: 32 }}>
            {addLabel}
          </Button>
        )}
      </Stack>
      {toolbar}
      {error && (
        <Box sx={{ mb: 1.5 }}>
          <LoadError message={error} onRetry={onRetry} />
        </Box>
      )}
      <List
        disablePadding
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          bgcolor: 'background.paper',
          opacity: loading && rows ? 0.6 : 1,
        }}
      >
        {rows === null &&
          Array.from({ length: 3 }, (_, i) => (
            <ListItem key={i} divider={i < 2}>
              <ListItemText primary={<Skeleton width="60%" />} secondary={<Skeleton width="35%" />} />
            </ListItem>
          ))}
        {rows?.length === 0 && (
          <ListItem>
            <ListItemText primary={emptyText} slotProps={{ primary: { color: 'text.secondary' } }} />
          </ListItem>
        )}
        {rows?.map((row, index) => {
          const text = (
            <ListItemText
              primary={
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
                  <Box component="span" sx={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {row.primary}
                  </Box>
                  {row.retired && <RetiredChip />}
                </Stack>
              }
              secondary={row.secondary}
              slotProps={{ secondary: { noWrap: true } }}
            />
          )
          const menu = <RowMenu name={row.primary} actions={row.actions} />
          return (
            <ListItem key={row.id} divider={index < rows.length - 1} disablePadding secondaryAction={menu}>
              {onSelect ? (
                <ListItemButton
                  selected={row.id === selectedId}
                  aria-current={row.id === selectedId ? 'true' : undefined}
                  onClick={() => onSelect(row.id)}
                  sx={{ pr: 7 }}
                >
                  {text}
                </ListItemButton>
              ) : (
                <Box sx={{ px: 2, py: 1, pr: 7, width: '100%' }}>{text}</Box>
              )}
            </ListItem>
          )
        })}
      </List>
    </Box>
  )
}

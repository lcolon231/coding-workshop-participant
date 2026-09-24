import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Badge from '@mui/material/Badge'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Typography from '@mui/material/Typography'
import { Bell } from '@phosphor-icons/react'
import { formatRelative } from '../lib/format'
import { MENU_LIMIT, POLL_INTERVAL_MS, describeNotification } from '../lib/notifications'
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../services/notifications'

const EMPTY = { items: [], unreadCount: 0 }

/**
 * The bell in the app bar: an unread badge and a menu of recent notifications.
 *
 * Engineers are told when an incident is assigned to them, admins when one is
 * reported, and reporters when theirs is resolved or closed by someone else.
 * The list is polled while the tab is visible and refreshed when it
 * regains focus, which is as close to live as a Lambda behind CloudFront
 * gets. A failed poll keeps whatever was last shown: a stale badge is better
 * than a flickering one, and the next poll will correct it.
 */
export default function NotificationBell() {
  const navigate = useNavigate()
  const [state, setState] = useState(EMPTY)
  const [anchor, setAnchor] = useState(null)
  const open = Boolean(anchor)

  const refresh = useCallback(() => {
    if (document.visibilityState === 'hidden') return
    listNotifications({ limit: MENU_LIMIT })
      .then((body) => setState({ items: body.items, unreadCount: body.unread_count }))
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, POLL_INTERVAL_MS)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [refresh])

  const openIncident = (notification) => {
    setAnchor(null)
    if (!notification.read_at) {
      const readAt = new Date().toISOString()
      setState((current) => ({
        items: current.items.map((item) =>
          item.id === notification.id ? { ...item, read_at: readAt } : item,
        ),
        unreadCount: Math.max(0, current.unreadCount - 1),
      }))
      // The row is marked on the server as the page changes; a failure here
      // only means the next poll shows it unread again.
      markNotificationRead(notification.id).catch(() => {})
    }
    navigate(`/incidents/${notification.incident_id}`)
  }

  const readAll = () => {
    const readAt = new Date().toISOString()
    setState((current) => ({
      items: current.items.map((item) => ({ ...item, read_at: item.read_at ?? readAt })),
      unreadCount: 0,
    }))
    markAllNotificationsRead().catch(() => {})
  }

  const { items, unreadCount } = state
  const label = unreadCount
    ? `Notifications, ${unreadCount} unread`
    : 'Notifications'

  return (
    <>
      <IconButton
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? 'notifications-menu' : undefined}
        onClick={(event) => {
          setAnchor(event.currentTarget)
          refresh()
        }}
        sx={{ color: 'text.secondary' }}
      >
        <Badge
          badgeContent={unreadCount}
          max={99}
          color="primary"
          invisible={unreadCount === 0}
          slotProps={{ badge: { 'aria-hidden': true } }}
        >
          <Bell size={22} />
        </Badge>
      </IconButton>
      <Menu
        id="notifications-menu"
        anchorEl={anchor}
        open={open}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 360, maxWidth: 'calc(100vw - 32px)', mt: 1 } } }}
      >
        <Box
          sx={{
            px: 2,
            py: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
          }}
        >
          <Typography sx={{ fontWeight: 600 }}>Notifications</Typography>
          <Button size="small" onClick={readAll} disabled={unreadCount === 0}>
            Mark all as read
          </Button>
        </Box>
        <Divider />
        {items.length === 0 ? (
          <Typography color="text.secondary" sx={{ px: 2, py: 2 }}>
            You&rsquo;re all caught up.
          </Typography>
        ) : (
          items.map((notification) => {
            const unread = !notification.read_at
            return (
              <MenuItem
                key={notification.id}
                onClick={() => openIncident(notification)}
                sx={{ alignItems: 'flex-start', gap: 1.5, py: 1.25, whiteSpace: 'normal' }}
              >
                <Box
                  aria-hidden="true"
                  sx={{
                    width: 8,
                    height: 8,
                    mt: '7px',
                    flexShrink: 0,
                    borderRadius: '50%',
                    bgcolor: unread ? 'primary.main' : 'transparent',
                  }}
                />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: unread ? 600 : 400 }}>
                    {describeNotification(notification)}
                    {unread && <Box component="span" sx={visuallyHidden}> (unread)</Box>}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatRelative(notification.created_at)}
                  </Typography>
                </Box>
              </MenuItem>
            )
          })
        )}
      </Menu>
    </>
  )
}

const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
}

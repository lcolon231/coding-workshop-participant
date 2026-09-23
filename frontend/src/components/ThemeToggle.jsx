import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import { useColorScheme } from '@mui/material/styles'
import { Moon, Sun } from '@phosphor-icons/react'

/**
 * Switches between the light and dark schemes. The choice is remembered by
 * MUI in local storage; until someone picks, the app follows the system.
 */
export default function ThemeToggle({ sx }) {
  const { mode, systemMode, setMode } = useColorScheme()
  const resolved = (mode === 'system' ? systemMode : mode) ?? 'light'
  const dark = resolved === 'dark'
  const label = dark ? 'Switch to light theme' : 'Switch to dark theme'
  return (
    <Tooltip title={label}>
      <IconButton aria-label={label} onClick={() => setMode(dark ? 'light' : 'dark')} sx={sx}>
        {dark ? <Sun size={22} /> : <Moon size={22} />}
      </IconButton>
    </Tooltip>
  )
}

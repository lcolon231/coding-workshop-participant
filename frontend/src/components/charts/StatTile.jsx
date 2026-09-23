import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'

/** One headline number with its label above and, optionally, a line under. */
export default function StatTile({ label, value, hint }) {
  const id = `tile-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <Box
      role="group"
      aria-labelledby={id}
      sx={{
        p: 2.5,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        minWidth: 0,
      }}
    >
      <Typography id={id} variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
        {label}
      </Typography>
      <Typography
        component="p"
        sx={{ fontSize: '2rem', fontWeight: 600, lineHeight: 1.2, letterSpacing: '-0.02em', mt: 0.5, fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </Typography>
      {hint && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {hint}
        </Typography>
      )}
    </Box>
  )
}

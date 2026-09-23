import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import { sequentialColor } from '../../lib/charts'

/**
 * Horizontal bars for a handful of counts, one hue, longest is largest.
 *
 * The list itself is the accessible form: every row reads as
 * "label, count", and the bars are decoration for sighted readers.
 */
export default function BarList({ title, items }) {
  const theme = useTheme()
  const max = Math.max(0, ...items.map((item) => item.count))
  const id = `bars-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <Box component="section" aria-labelledby={id} sx={{ minWidth: 0 }}>
      <Typography component="h3" variant="body1" id={id} sx={{ fontWeight: 600, mb: 1.5 }}>
        {title}
      </Typography>
      {max === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Nothing in this range.
        </Typography>
      ) : (
        <Box component="ol" sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 1 }}>
          {items.map((item) => (
            <Box
              component="li"
              key={item.key}
              sx={{ display: 'grid', gridTemplateColumns: 'minmax(72px, 30%) 1fr auto', gap: 1.5, alignItems: 'center' }}
            >
              <Typography variant="body2" noWrap>
                {item.key}
              </Typography>
              <Box
                aria-hidden="true"
                sx={{ height: 10, borderRadius: 999, bgcolor: (theme.vars ?? theme).palette.chart.track, overflow: 'hidden' }}
              >
                <Box
                  sx={{
                    height: '100%',
                    width: `${(item.count / max) * 100}%`,
                    minWidth: item.count > 0 ? 4 : 0,
                    borderRadius: 999,
                    bgcolor: sequentialColor(theme),
                    transition: 'width 240ms ease',
                  }}
                />
              </Box>
              <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: '2ch', textAlign: 'right' }}>
                {item.count}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  )
}

import { useState } from 'react'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import { seriesColor } from '../../lib/charts'

const SIZE = 200
const RING = 30
const GAP = 2
/** Past this many slices the tail folds into one, rather than inventing hues. */
const MAX_SLICES = 7
const OTHER = 'Other'

/** A ring segment from `a0` to `a1` (radians, clockwise from twelve o'clock). */
function arcPath(cx, cy, outer, inner, a0, a1) {
  const sweep = Math.min(a1 - a0, 2 * Math.PI - 1e-4)
  const end = a0 + sweep
  const large = sweep > Math.PI ? 1 : 0
  const point = (radius, angle) => `${(cx + radius * Math.sin(angle)).toFixed(2)},${(cy - radius * Math.cos(angle)).toFixed(2)}`
  return [
    `M${point(outer, a0)}`,
    `A${outer},${outer} 0 ${large} 1 ${point(outer, end)}`,
    `L${point(inner, end)}`,
    `A${inner},${inner} 0 ${large} 0 ${point(inner, a0)}`,
    'Z',
  ].join('')
}

/** Every slice with a value, largest first, the tail past `MAX_SLICES` folded into "Other". */
function fold(slices) {
  const drawn = slices.filter((slice) => slice.value > 0).sort((a, b) => b.value - a.value)
  if (drawn.length <= MAX_SLICES) return drawn
  const head = drawn.slice(0, MAX_SLICES - 1)
  const tail = drawn.slice(MAX_SLICES - 1)
  return [
    ...head,
    {
      key: OTHER,
      label: `${OTHER} (${tail.length})`,
      value: tail.reduce((sum, slice) => sum + slice.value, 0),
      other: true,
    },
  ]
}

/**
 * A donut of one number per named thing (a building, an engineer), the
 * total in the hole, a legend beside it with each share.
 *
 * Every slice is a keyboard-reachable hit target with a plain-text summary;
 * hovering or focusing one shows its numbers in a tooltip, including any
 * `detail` rows the slice carries (finished and open, say).
 *
 * `slices`: `{ key, label, role?, value, slot?, detail?: [{ name, value, slot }] }`.
 * `slot` pins a colour so the same thing keeps its hue across charts; slices
 * without one take the next free slot in rank order. `role` is a short
 * qualifier (an engineer's specialty) shown under the label in the legend
 * and the tooltip, and read out with the slice.
 */
export default function PieChart({ slices, ariaLabel, unit = 'incidents' }) {
  const theme = useTheme()
  const [active, setActive] = useState(null)
  const paper = (theme.vars ?? theme).palette.background.paper
  const ink = (theme.vars ?? theme).palette.text
  const track = (theme.vars ?? theme).palette.chart.track

  const drawn = fold(slices)
  const total = drawn.reduce((sum, slice) => sum + slice.value, 0)
  const cx = SIZE / 2
  const outer = SIZE / 2
  const inner = outer - RING
  const segments = drawn.reduce((laid, slice, index) => {
    const start = index === 0 ? 0 : laid[index - 1].start + laid[index - 1].sweep
    const sweep = total > 0 ? (slice.value / total) * 2 * Math.PI : 0
    const slot = slice.slot ?? laid.filter((done) => done.free).length
    const color = slice.other ? track : seriesColor(theme, slot)
    const share = total > 0 ? Math.round((slice.value / total) * 100) : 0
    return [...laid, { ...slice, start, sweep, color, share, free: slice.slot === undefined }]
  }, [])
  const current = active === null ? null : segments[active]

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={3}
      useFlexGap
      sx={{ alignItems: { xs: 'center', sm: 'flex-start' } }}
      onMouseLeave={() => setActive(null)}
    >
      <Box sx={{ position: 'relative', flexShrink: 0, width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={ariaLabel} style={{ display: 'block', fontFamily: 'inherit' }}>
          {segments.map((segment, index) => {
            const who = segment.role ? `${segment.label} (${segment.role})` : segment.label
            const summary = `${who}: ${segment.value} ${segment.value === 1 ? unit.replace(/s$/, '') : unit}, ${segment.share}%`
            const dim = active !== null && active !== index
            return (
              <path
                key={segment.key}
                d={arcPath(cx, cx, outer, inner, segment.start, segment.start + segment.sweep)}
                fill={segment.color}
                stroke={paper}
                strokeWidth={GAP}
                opacity={dim ? 0.45 : 1}
                tabIndex={0}
                aria-label={summary}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
                style={{ outline: 'none', cursor: 'default' }}
              >
                <title>{summary}</title>
              </path>
            )
          })}
          <text
            x={cx}
            y={cx - 2}
            textAnchor="middle"
            fontSize={30}
            fontWeight={600}
            fill={ink.primary}
            style={{ fontVariantNumeric: 'tabular-nums', pointerEvents: 'none' }}
          >
            {total}
          </text>
          <text x={cx} y={cx + 18} textAnchor="middle" fontSize={12} fill={ink.secondary} style={{ pointerEvents: 'none' }}>
            {unit}
          </text>
        </svg>
        {current && (
          <Box
            role="status"
            sx={{
              position: 'absolute',
              left: '50%',
              top: '100%',
              transform: 'translate(-50%, 8px)',
              minWidth: 160,
              maxWidth: 240,
              px: 1.5,
              py: 1,
              borderRadius: 1,
              bgcolor: 'background.paper',
              border: 1,
              borderColor: 'divider',
              boxShadow: 2,
              pointerEvents: 'none',
              fontSize: '0.8125rem',
              zIndex: 1,
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {current.label}
            </Typography>
            {current.role && (
              <Typography variant="body2" color="text.secondary">
                {current.role}
              </Typography>
            )}
            {(current.detail ?? [])
              .filter((row) => row.value > 0)
              .map((row) => (
                <Stack key={row.name} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                  <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                    {row.name}
                  </Typography>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {row.value}
                  </Typography>
                </Stack>
              ))}
            <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 500 }}>
              {current.value} of {total} · {current.share}%
            </Typography>
          </Box>
        )}
      </Box>
      <Box
        component="ul"
        aria-label="Slices"
        sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 0.75, minWidth: 0, flex: 1, maxWidth: 360, alignSelf: 'center' }}
      >
        {segments.map((segment, index) => (
          <Box
            component="li"
            key={segment.key}
            onMouseEnter={() => setActive(index)}
            sx={{
              display: 'grid',
              gridTemplateColumns: 'auto 1fr auto auto',
              gap: 1.5,
              alignItems: 'center',
              opacity: active !== null && active !== index ? 0.6 : 1,
            }}
          >
            <Box
              aria-hidden="true"
              sx={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                bgcolor: segment.color,
                border: segment.other ? 1 : 0,
                borderColor: 'divider',
              }}
            />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {segment.label}
              </Typography>
              {segment.role && (
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                  {segment.role}
                </Typography>
              )}
            </Box>
            <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
              {segment.value}
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                fontVariantNumeric: 'tabular-nums',
                minWidth: '4ch',
                textAlign: 'right',
              }}
            >
              {segment.share}%
            </Typography>
          </Box>
        ))}
      </Box>
    </Stack>
  )
}

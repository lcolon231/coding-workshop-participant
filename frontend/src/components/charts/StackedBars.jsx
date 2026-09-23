import { useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import { seriesColor } from '../../lib/charts'
import { useWidth } from '../../lib/useWidth'

const ROW = 34
const BAR = 18
const MARGIN = { top: 8, right: 40, bottom: 24 }
const GAP = 2
const RADIUS = 4

/** Whole-number ticks, at most four of them above zero, and the round top they reach. */
function axis(value) {
  if (value <= 4) return { max: 4, step: 1 }
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 5, 10].map((unit) => unit * power).find((unit) => unit * 4 >= value) ?? power * 10
  return { max: Math.ceil(value / step) * step, step }
}

/** Roughly how many 12px characters fit in `pixels`. */
function fit(label, pixels) {
  const chars = Math.max(4, Math.floor(pixels / 6.8))
  return label.length > chars ? `${label.slice(0, chars - 1)}…` : label
}

/** A bar segment: square at the baseline, rounded only at the data end. */
function segmentPath(x, y, width, height, rounded) {
  if (!rounded || width <= RADIUS) return `M${x},${y}h${width}v${height}h${-width}z`
  const r = Math.min(RADIUS, height / 2)
  return `M${x},${y}h${width - r}a${r},${r} 0 0 1 ${r},${r}v${height - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(width - r)}z`
}

function Legend({ series, theme }) {
  return (
    <Stack component="ul" direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 1.5, listStyle: 'none', m: 0, p: 0 }} aria-label="Series">
      {series.map((entry) => (
        <Stack component="li" key={entry.name} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
          <Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: seriesColor(theme, entry.slot) }} />
          <Typography variant="body2">{entry.name}</Typography>
        </Stack>
      ))}
    </Stack>
  )
}

function DataTable({ rows, series, label, extras }) {
  return (
    <Table size="small" aria-label={label}>
      <TableHead>
        <TableRow>
          <TableCell>{label}</TableCell>
          {series.map((entry) => (
            <TableCell key={entry.name} align="right">
              {entry.name}
            </TableCell>
          ))}
          <TableCell align="right">Total</TableCell>
          {extras.map((extra) => (
            <TableCell key={extra.name} align="right">
              {extra.name}
            </TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell sx={{ fontWeight: 500 }}>{row.label}</TableCell>
            {series.map((entry) => (
              <TableCell key={entry.name} align="right">
                {row.values[entry.name]}
              </TableCell>
            ))}
            <TableCell align="right">{row.total}</TableCell>
            {extras.map((extra) => (
              <TableCell key={extra.name} align="right">
                {extra.value(row)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * One horizontal stacked bar per named thing (a building, an engineer),
 * longest first, one colour slot per series, the total at the bar's tip.
 *
 * Every row band is a keyboard-reachable hit target with a plain-text
 * summary; hovering or focusing one shows the same numbers in a tooltip,
 * plus any `extras` (a count that is not a segment, like "Critical").
 * `table` swaps the picture for the numbers.
 *
 * `rows`: `{ key, label, values: { [series]: n }, total }`.
 */
export default function StackedBars({ rows, series, extras = [], table = false, ariaLabel, tableLabel }) {
  const theme = useTheme()
  const ref = useRef(null)
  const width = useWidth(ref)
  const [active, setActive] = useState(null)

  const legend = <Legend series={series} theme={theme} />
  if (table) {
    return (
      <Stack spacing={2}>
        {legend}
        <DataTable rows={rows} series={series} label={tableLabel} extras={extras} />
      </Stack>
    )
  }

  const labelWidth = Math.min(160, Math.max(72, Math.round(width * 0.28)))
  const innerW = Math.max(0, width - labelWidth - MARGIN.right)
  const innerH = rows.length * ROW
  const height = MARGIN.top + innerH + MARGIN.bottom
  const { max, step } = axis(Math.max(0, ...rows.map((row) => row.total)))
  const scale = (value) => (value / max) * innerW
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)
  const ink = (theme.vars ?? theme).palette.text
  const divider = (theme.vars ?? theme).palette.divider
  const current = active === null ? null : rows[active]

  return (
    <Stack spacing={2}>
      {legend}
      <Box ref={ref} sx={{ position: 'relative', width: '100%' }} onMouseLeave={() => setActive(null)}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={ariaLabel}
          style={{ display: 'block', maxWidth: '100%', fontFamily: 'inherit' }}
        >
          {ticks.map((tick) => {
            const x = labelWidth + scale(tick)
            return (
              <g key={tick}>
                <line x1={x} x2={x} y1={MARGIN.top} y2={MARGIN.top + innerH} stroke={divider} strokeWidth={1} />
                <text x={x} y={height - 6} textAnchor="middle" fontSize={11} fill={ink.secondary}>
                  {tick}
                </text>
              </g>
            )
          })}
          {rows.map((row, index) => {
            const y0 = MARGIN.top + index * ROW
            const y = y0 + (ROW - BAR) / 2
            let left = labelWidth
            const painted = series.filter((entry) => row.values[entry.name] > 0)
            const segments = painted.map((entry, position) => {
              const value = row.values[entry.name]
              const x = left
              const w = scale(value)
              left += w
              return { entry, value, x, w, last: position === painted.length - 1 }
            })
            const summary = `${row.label}: ${row.total} incident${row.total === 1 ? '' : 's'}`
            const dim = active !== null && active !== index
            return (
              <g key={row.key}>
                <text x={labelWidth - 10} y={y0 + ROW / 2 + 4} textAnchor="end" fontSize={12} fill={ink.primary}>
                  {fit(row.label, labelWidth - 10)}
                </text>
                {segments.map((segment) => (
                  <path
                    key={segment.entry.name}
                    d={segmentPath(segment.x, y, Math.max(0, segment.w - (segment.last ? 0 : GAP)), BAR, segment.last)}
                    fill={seriesColor(theme, segment.entry.slot)}
                    opacity={dim ? 0.45 : 1}
                  />
                ))}
                {row.total > 0 && (
                  <text x={left + 8} y={y0 + ROW / 2 + 4} fontSize={12} fill={ink.secondary} style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {row.total}
                  </text>
                )}
                <rect
                  x={0}
                  y={y0}
                  width={width}
                  height={ROW}
                  fill="transparent"
                  tabIndex={0}
                  aria-label={summary}
                  onMouseEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                  style={{ outline: 'none', cursor: 'default' }}
                >
                  <title>{summary}</title>
                </rect>
              </g>
            )
          })}
        </svg>
        {current && (
          <Box
            role="status"
            sx={{
              position: 'absolute',
              left: labelWidth + Math.min(scale(current.total), Math.max(0, innerW - 200)) + 12,
              top: MARGIN.top + active * ROW + ROW,
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
            {series
              .filter((entry) => current.values[entry.name] > 0)
              .map((entry) => (
                <Stack key={entry.name} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                  <Box aria-hidden="true" sx={{ width: 8, height: 8, borderRadius: 0.5, bgcolor: seriesColor(theme, entry.slot) }} />
                  <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                    {entry.name}
                  </Typography>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {current.values[entry.name]}
                  </Typography>
                </Stack>
              ))}
            <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 500 }}>
              Total {current.total}
            </Typography>
            {extras.map((extra) => (
              <Typography key={extra.name} variant="body2" color="text.secondary">
                {extra.name} {extra.value(current)}
              </Typography>
            ))}
          </Box>
        )}
      </Box>
    </Stack>
  )
}

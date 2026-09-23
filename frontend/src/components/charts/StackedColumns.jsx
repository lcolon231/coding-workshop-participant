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
import { bucketLabel } from '../../lib/reports'
import { useWidth } from '../../lib/useWidth'

const HEIGHT = 260
const MARGIN = { top: 12, right: 8, bottom: 28, left: 36 }
const GAP = 2

/** A round upper bound with about four gridlines under it. */
function niceMax(value) {
  if (value <= 4) return 4
  const power = 10 ** Math.floor(Math.log10(value))
  const unit = [1, 2, 4, 5, 10].map((step) => step * power).find((step) => step * 4 >= value) ?? power * 10
  return Math.ceil(value / unit) * unit
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

function DataTable({ buckets, series }) {
  return (
    <Table size="small" aria-label="Incidents per bucket">
      <TableHead>
        <TableRow>
          <TableCell>Bucket starting</TableCell>
          {series.map((entry) => (
            <TableCell key={entry.name} align="right">
              {entry.name}
            </TableCell>
          ))}
          <TableCell align="right">Total</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {buckets.map((bucket) => (
          <TableRow key={bucket.bucket_start}>
            <TableCell>{bucketLabel(bucket.bucket_start)}</TableCell>
            {series.map((entry) => (
              <TableCell key={entry.name} align="right">
                {bucket.values[entry.name]}
              </TableCell>
            ))}
            <TableCell align="right">{bucket.total}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/**
 * Incidents per bucket as stacked columns, one colour slot per series.
 *
 * Every column band is a keyboard-reachable hit target with a plain-text
 * summary; hovering or focusing one shows the same numbers in a tooltip.
 * `table` swaps the picture for the numbers.
 */
export default function StackedColumns({ buckets, series, table = false, ariaLabel }) {
  const theme = useTheme()
  const ref = useRef(null)
  const width = useWidth(ref)
  const [active, setActive] = useState(null)

  const legend = <Legend series={series} theme={theme} />
  if (table) {
    return (
      <Stack spacing={2}>
        {legend}
        <DataTable buckets={buckets} series={series} />
      </Stack>
    )
  }

  const innerW = Math.max(0, width - MARGIN.left - MARGIN.right)
  const innerH = HEIGHT - MARGIN.top - MARGIN.bottom
  const band = buckets.length > 0 ? innerW / buckets.length : innerW
  const column = Math.max(2, Math.min(band * 0.7, 48))
  const max = niceMax(Math.max(0, ...buckets.map((bucket) => bucket.total)))
  const scale = (value) => (value / max) * innerH
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => fraction * max)
  const labelEvery = Math.max(1, Math.ceil(buckets.length / Math.max(1, Math.floor(innerW / 80))))
  const ink = (theme.vars ?? theme).palette.text
  const divider = (theme.vars ?? theme).palette.divider

  const current = active === null ? null : buckets[active]

  return (
    <Stack spacing={2}>
      {legend}
      <Box ref={ref} sx={{ position: 'relative', width: '100%' }} onMouseLeave={() => setActive(null)}>
        <svg
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          role="img"
          aria-label={ariaLabel}
          style={{ display: 'block', maxWidth: '100%', fontFamily: 'inherit' }}
        >
          {ticks.map((tick) => {
            const y = MARGIN.top + innerH - scale(tick)
            return (
              <g key={tick}>
                <line x1={MARGIN.left} x2={MARGIN.left + innerW} y1={y} y2={y} stroke={divider} strokeWidth={1} />
                <text x={MARGIN.left - 8} y={y + 4} textAnchor="end" fontSize={11} fill={ink.secondary}>
                  {tick}
                </text>
              </g>
            )
          })}
          {buckets.map((bucket, index) => {
            const x0 = MARGIN.left + index * band
            const x = x0 + (band - column) / 2
            let top = MARGIN.top + innerH
            const segments = series.map((entry) => {
              const value = bucket.values[entry.name]
              const height = scale(value)
              const y = top - height
              top = y
              return { entry, value, y, height }
            })
            const summary = `${bucketLabel(bucket.bucket_start)}: ${bucket.total} incident${bucket.total === 1 ? '' : 's'}`
            return (
              <g key={bucket.bucket_start}>
                {segments
                  .filter((segment) => segment.height > 0)
                  .map((segment) => (
                    <rect
                      key={segment.entry.name}
                      x={x}
                      y={segment.y + GAP / 2}
                      width={column}
                      height={Math.max(0, segment.height - GAP)}
                      rx={2}
                      fill={seriesColor(theme, segment.entry.slot)}
                      opacity={active === null || active === index ? 1 : 0.45}
                    />
                  ))}
                {index % labelEvery === 0 && (
                  <text
                    x={x0 + band / 2}
                    y={HEIGHT - 8}
                    textAnchor="middle"
                    fontSize={11}
                    fill={ink.secondary}
                  >
                    {bucketLabel(bucket.bucket_start)}
                  </text>
                )}
                <rect
                  x={x0}
                  y={MARGIN.top}
                  width={band}
                  height={innerH}
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
              left: `${((MARGIN.left + (active + 0.5) * band) / Math.max(1, width)) * 100}%`,
              top: 0,
              transform: 'translate(-50%, 0)',
              maxWidth: 220,
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
              {bucketLabel(current.bucket_start)}
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
          </Box>
        )}
      </Box>
    </Stack>
  )
}

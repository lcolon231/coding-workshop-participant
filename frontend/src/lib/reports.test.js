import { describe, expect, it, vi } from 'vitest'
import {
  bucketStarts,
  buildSeries,
  collectAll,
  countOf,
  csvCell,
  defaultRange,
  exportFilename,
  incidentsCsv,
  openBacklog,
  pivotVolume,
  presetFor,
  rangeEnding,
} from './reports'

const NOW = new Date('2026-09-23T10:00:00Z')

describe('ranges', () => {
  it('counts the inclusive days ending today', () => {
    expect(rangeEnding(NOW, 7)).toEqual({ from: '2026-09-17', to: '2026-09-23' })
    expect(defaultRange(NOW)).toEqual({ from: '2026-08-25', to: '2026-09-23' })
  })

  it('recognises a preset by its exact range', () => {
    expect(presetFor({ from: '2026-08-25', to: '2026-09-23' }, NOW)?.days).toBe(30)
    expect(presetFor({ from: '2026-08-01', to: '2026-09-23' }, NOW)).toBeUndefined()
  })
})

describe('buildSeries', () => {
  it('keeps the domain order and slot for statuses even when some are absent', () => {
    const rows = [{ group: 'Resolved' }, { group: 'Open' }]
    expect(buildSeries('status', rows)).toEqual([
      { name: 'Open', slot: 0 },
      { name: 'Resolved', slot: 3 },
    ])
  })

  it('sorts categories and folds the tail into Other', () => {
    const rows = ['Zeta', 'HVAC', 'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Eta'].map((group) => ({ group }))
    const series = buildSeries('category', rows)
    expect(series.map((entry) => entry.name)).toEqual(['Alpha', 'Beta', 'Delta', 'Epsilon', 'Eta', 'Gamma', 'Other'])
    expect(series.at(-1)).toEqual({ name: 'Other', slot: 6 })
  })
})

describe('bucketStarts', () => {
  it('lists every day inclusive', () => {
    expect(bucketStarts('2026-09-21', '2026-09-23', 'day')).toEqual(['2026-09-21', '2026-09-22', '2026-09-23'])
  })

  it('aligns weeks to the Monday on or before the start, as the API does', () => {
    // 2026-09-23 is a Wednesday; the Monday before is the 21st.
    expect(bucketStarts('2026-09-23', '2026-10-06', 'week')).toEqual(['2026-09-21', '2026-09-28', '2026-10-05'])
    expect(bucketStarts('2026-09-21', '2026-09-27', 'week')).toEqual(['2026-09-21'])
  })
})

describe('pivotVolume', () => {
  it('zero-fills buckets and folds unknown groups into Other', () => {
    const series = [
      { name: 'HVAC', slot: 0 },
      { name: 'Other', slot: 6 },
    ]
    const rows = [
      { bucket_start: '2026-09-21', group: 'HVAC', count: 2 },
      { bucket_start: '2026-09-21', group: 'Printer', count: 1 },
      { bucket_start: '2026-09-23', group: 'HVAC', count: 4 },
    ]
    expect(pivotVolume(rows, { from: '2026-09-21', to: '2026-09-23', interval: 'day', series })).toEqual([
      { bucket_start: '2026-09-21', values: { HVAC: 2, Other: 1 }, total: 3 },
      { bucket_start: '2026-09-22', values: { HVAC: 0, Other: 0 }, total: 0 },
      { bucket_start: '2026-09-23', values: { HVAC: 4, Other: 0 }, total: 4 },
    ])
  })

  it('drops a group that is neither a series nor foldable', () => {
    const series = [{ name: 'Open', slot: 0 }]
    const rows = [{ bucket_start: '2026-09-21', group: 'Closed', count: 9 }]
    expect(pivotVolume(rows, { from: '2026-09-21', to: '2026-09-21', interval: 'day', series })).toEqual([
      { bucket_start: '2026-09-21', values: { Open: 0 }, total: 0 },
    ])
  })
})

describe('summary helpers', () => {
  const summary = {
    by_status: [
      { key: 'Open', count: 3 },
      { key: 'In Progress', count: 2 },
      { key: 'Blocked', count: 0 },
      { key: 'Resolved', count: 1 },
      { key: 'Closed', count: 4 },
    ],
  }
  it('counts everything not closed as backlog', () => {
    expect(openBacklog(summary)).toBe(6)
    expect(countOf(summary.by_status, 'Closed')).toBe(4)
    expect(countOf(summary.by_status, 'Missing')).toBe(0)
  })
})

describe('csv export', () => {
  it('quotes only the cells that need it', () => {
    expect(csvCell('plain')).toBe('plain')
    expect(csvCell(null)).toBe('')
    expect(csvCell('a, b')).toBe('"a, b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell('two\nlines')).toBe('"two\nlines"')
  })

  it('writes a header and one CRLF-terminated row per incident with building names', () => {
    const names = new Map([['b-1', 'HQ, North']])
    const csv = incidentsCsv(
      [
        {
          id: 'i1',
          title: 'Leak',
          status: 'Open',
          priority: 'Low',
          building_id: 'b-1',
          reporter: { full_name: 'Eve' },
          assignee: null,
          created_at: '2026-09-01T00:00:00Z',
          acknowledged_at: null,
          resolved_at: null,
          closed_at: null,
        },
        { id: 'i2', title: 'Other', status: 'Open', priority: 'Low', building_id: 'b-2', created_at: 'x' },
      ],
      names,
    )
    expect(csv).toBe(
      'id,title,status,priority,building,reporter,assignee,reported_at,acknowledged_at,resolved_at,closed_at\r\n' +
        'i1,Leak,Open,Low,"HQ, North",Eve,,2026-09-01T00:00:00Z,,,\r\n' +
        'i2,Other,Open,Low,b-2,,,x,,,\r\n',
    )
  })

  it('walks pages until the total is reached and stops on an empty page', async () => {
    const pages = [
      { items: [1, 2], total: 3 },
      { items: [3], total: 3 },
    ]
    const fetchPage = vi.fn(async () => pages.shift())
    expect(await collectAll(fetchPage)).toEqual([1, 2, 3])
    expect(fetchPage.mock.calls.map(([paging]) => paging)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 2 },
    ])

    const shrinking = vi.fn(async () => ({ items: [], total: 5 }))
    expect(await collectAll(shrinking)).toEqual([])
    expect(shrinking).toHaveBeenCalledTimes(1)
  })

  it('names the file after the range', () => {
    expect(exportFilename({ from: '2026-08-25', to: '2026-09-23' })).toBe('incidents-2026-08-25-to-2026-09-23.csv')
  })
})

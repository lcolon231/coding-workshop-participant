import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { render } from '@testing-library/react'
import StackedBars from './StackedBars'
import { theme } from '../../theme'

const SERIES = [
  { name: 'Finished', slot: 0 },
  { name: 'Open', slot: 1 },
]
const ROWS = [
  { key: 'hq', label: 'Headquarters', values: { Finished: 5, Open: 2 }, total: 7, critical: 1 },
  { key: 'rva', label: 'Riverside Annex', values: { Finished: 0, Open: 3 }, total: 3, critical: 0 },
  { key: 'quiet', label: 'Quiet House', values: { Finished: 0, Open: 0 }, total: 0, critical: 0 },
]
const EXTRAS = [{ name: 'Critical', value: (row) => row.critical }]

function renderBars(props = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <StackedBars rows={ROWS} series={SERIES} extras={EXTRAS} ariaLabel="Incidents per building" tableLabel="Building" {...props} />
    </ThemeProvider>,
  )
}

describe('StackedBars', () => {
  it('draws one labelled, focusable bar per row with a legend', async () => {
    renderBars()

    const chart = screen.getByRole('img', { name: 'Incidents per building' })
    const legend = screen.getByRole('list', { name: 'Series' })
    expect(within(legend).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Finished', 'Open'])
    expect(within(chart).getByLabelText('Headquarters: 7 incidents')).toBeInTheDocument()
    expect(within(chart).getByLabelText('Quiet House: 0 incidents')).toBeInTheDocument()
    // Two painted segments for HQ, one for the annex, none for the quiet one.
    expect(chart.querySelectorAll('path')).toHaveLength(3)

    await userEvent.tab()
    const tooltip = screen.getByRole('status')
    expect(tooltip).toHaveTextContent('Headquarters')
    expect(tooltip).toHaveTextContent('Finished5')
    expect(tooltip).toHaveTextContent('Open2')
    expect(tooltip).toHaveTextContent('Total 7')
    expect(tooltip).toHaveTextContent('Critical 1')
  })

  it('swaps the picture for a table with the extras as columns', () => {
    renderBars({ table: true })

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    const table = screen.getByRole('table', { name: 'Building' })
    const header = within(table).getAllByRole('columnheader').map((cell) => cell.textContent)
    expect(header).toEqual(['Building', 'Finished', 'Open', 'Total', 'Critical'])
    const annex = within(table).getByText('Riverside Annex').closest('tr')
    expect(within(annex).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Riverside Annex', '0', '3', '3', '0'])
  })
})

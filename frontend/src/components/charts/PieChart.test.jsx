import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import PieChart from './PieChart'
import { theme } from '../../theme'

function renderChart(props) {
  return render(
    <ThemeProvider theme={theme}>
      <PieChart ariaLabel="Incidents per building" {...props} />
    </ThemeProvider>,
  )
}

const SLICES = [
  { key: 'hq', label: 'Headquarters', value: 7, detail: [{ name: 'Finished', value: 5 }, { name: 'Open', value: 2 }] },
  { key: 'annex', label: 'Riverside Annex', role: 'North campus', value: 1, detail: [{ name: 'Finished', value: 0 }, { name: 'Open', value: 1 }] },
  { key: 'empty', label: 'Warehouse', value: 0 },
]

describe('PieChart', () => {
  it('draws only the slices with a value, largest first, and reads each one out', () => {
    renderChart({ slices: SLICES })
    const chart = screen.getByRole('img', { name: 'Incidents per building' })
    const labels = Array.from(chart.querySelectorAll('path[aria-label]')).map((path) => path.getAttribute('aria-label'))
    expect(labels).toEqual(['Headquarters: 7 incidents, 88%', 'Riverside Annex (North campus): 1 incident, 13%'])
    expect(within(chart).getByText('8')).toBeInTheDocument()
    const legend = within(screen.getByRole('list', { name: 'Slices' })).getAllByRole('listitem')
    expect(legend.map((item) => item.textContent)).toEqual(['Headquarters788%', 'Riverside AnnexNorth campus113%'])
  })

  it('shows the numbers of the hovered or focused slice in a tooltip, with its detail rows', async () => {
    renderChart({ slices: SLICES })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    await userEvent.hover(screen.getByLabelText(/^Riverside Annex/))
    const tooltip = screen.getByRole('status')
    expect(tooltip).toHaveTextContent('Riverside Annex')
    expect(tooltip).toHaveTextContent('North campus')
    // A zero detail row is left out; the non-zero one is shown.
    expect(within(tooltip).queryByText('Finished')).not.toBeInTheDocument()
    expect(within(tooltip).getByText('Open')).toBeInTheDocument()
    expect(tooltip).toHaveTextContent('1 of 8 · 13%')

    await userEvent.unhover(screen.getByRole('img', { name: 'Incidents per building' }).parentElement.parentElement)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    await userEvent.tab()
    expect(screen.getByRole('status')).toHaveTextContent('Headquarters')
    await userEvent.tab()
    await userEvent.tab()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    await userEvent.hover(within(screen.getByRole('list', { name: 'Slices' })).getAllByRole('listitem')[0])
    expect(screen.getByRole('status')).toHaveTextContent('Headquarters')
  })

  it('folds the tail past seven slices into "Other" rather than inventing hues', () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ key: `k${i}`, label: `Building ${i}`, value: 10 - i }))
    renderChart({ slices: many, unit: 'critical' })
    const chart = screen.getByRole('img', { name: 'Incidents per building' })
    const labels = Array.from(chart.querySelectorAll('path[aria-label]')).map((path) => path.getAttribute('aria-label'))
    expect(labels).toHaveLength(7)
    expect(labels.at(-1)).toBe('Other (4): 10 critical, 18%')
    expect(within(chart).getByText('critical')).toBeInTheDocument()
  })
})

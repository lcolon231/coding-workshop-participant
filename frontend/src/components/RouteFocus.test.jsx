import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import RouteFocus from './RouteFocus'

function Page({ name, to }) {
  return (
    <>
      <Link to={to}>Go to {to}</Link>
      <main id="main" tabIndex={-1}>
        {name}
      </main>
    </>
  )
}

function renderApp(initial = '/') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <RouteFocus />
      <Routes>
        <Route path="/" element={<Page name="Home" to="/reports" />} />
        <Route path="/reports" element={<Page name="Reports" to="/" />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RouteFocus', () => {
  it('leaves focus alone on the first render', () => {
    renderApp()
    expect(screen.getByRole('main')).not.toHaveFocus()
  })

  it('moves focus to the page after a navigation', async () => {
    renderApp()
    await userEvent.click(screen.getByRole('link', { name: 'Go to /reports' }))
    expect(screen.getByRole('main')).toHaveTextContent('Reports')
    expect(screen.getByRole('main')).toHaveFocus()
  })
})

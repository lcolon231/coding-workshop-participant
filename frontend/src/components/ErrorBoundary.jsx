import { Component } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

/**
 * The last line before a blank page.
 *
 * A render error anywhere below unmounts the whole tree, so this catches it
 * and says so, with a way back: "Try again" remounts the children (enough
 * for a one-off bad render), "Reload" starts the app over. The error itself
 * goes to the console for whoever is debugging; the person sees no stack.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error', error, info?.componentStack)
  }

  reset = () => {
    this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <Box sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 2 }}>
        <Stack spacing={2} alignItems="flex-start" sx={{ maxWidth: 440 }} role="alert">
          <Typography component="h1" variant="h1">
            Something went wrong
          </Typography>
          <Typography color="text.secondary">
            This page hit an error it could not recover from. Nothing you submitted was lost on
            the server.
          </Typography>
          <Stack direction="row" spacing={1.5}>
            <Button variant="contained" onClick={this.reset}>
              Try again
            </Button>
            <Button variant="outlined" onClick={() => window.location.reload()}>
              Reload
            </Button>
          </Stack>
        </Stack>
      </Box>
    )
  }
}

import FormControl from '@mui/material/FormControl'
import FormHelperText from '@mui/material/FormHelperText'
import FormLabel from '@mui/material/FormLabel'
import OutlinedInput from '@mui/material/OutlinedInput'

/**
 * A labelled input: label above, helper text and error text below.
 *
 * The label is a real `<label for>`, never a placeholder. Helper and error
 * text are both announced through `aria-describedby`.
 */
export default function Field({
  id,
  name = id,
  label,
  helperText,
  error,
  endAdornment,
  inputAttributes,
  ...inputProps
}) {
  const helpId = helperText ? `${id}-help` : null
  const errorId = error ? `${id}-error` : null
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <FormControl fullWidth error={Boolean(error)}>
      <FormLabel
        htmlFor={id}
        sx={{
          mb: 0.75,
          fontWeight: 500,
          color: 'text.primary',
          '&.Mui-focused, &.Mui-error': { color: 'text.primary' },
        }}
      >
        {label}
      </FormLabel>
      <OutlinedInput
        id={id}
        name={name}
        endAdornment={endAdornment}
        slotProps={{ input: { 'aria-describedby': describedBy, ...inputAttributes } }}
        {...inputProps}
      />
      {helperText && (
        <FormHelperText id={helpId} error={false}>
          {helperText}
        </FormHelperText>
      )}
      {error && <FormHelperText id={errorId}>{error}</FormHelperText>}
    </FormControl>
  )
}

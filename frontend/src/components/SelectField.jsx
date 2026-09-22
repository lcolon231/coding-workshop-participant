import FormControl from '@mui/material/FormControl'
import FormHelperText from '@mui/material/FormHelperText'
import FormLabel from '@mui/material/FormLabel'
import OutlinedInput from '@mui/material/OutlinedInput'
import Select from '@mui/material/Select'

/**
 * A labelled native `<select>`: label above, helper and error text below.
 *
 * Native because it works with the keyboard and on phones without any extra
 * code, and because a test can drive it with `selectOptions`. Children are
 * `<option>` and `<optgroup>` elements.
 */
export default function SelectField({
  id,
  name = id,
  label,
  helperText,
  error,
  children,
  ...selectProps
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
      <Select
        native
        input={<OutlinedInput />}
        inputProps={{ id, name, 'aria-describedby': describedBy }}
        {...selectProps}
      >
        {children}
      </Select>
      {helperText && (
        <FormHelperText id={helpId} error={false}>
          {helperText}
        </FormHelperText>
      )}
      {error && <FormHelperText id={errorId}>{error}</FormHelperText>}
    </FormControl>
  )
}

import { useState } from 'react'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import { Eye, EyeSlash } from '@phosphor-icons/react'
import Field from './Field'

/** A password input with a show/hide toggle. */
export default function PasswordField(props) {
  const [visible, setVisible] = useState(false)
  return (
    <Field
      {...props}
      type={visible ? 'text' : 'password'}
      endAdornment={
        <InputAdornment position="end">
          <IconButton
            aria-label={visible ? 'Hide password' : 'Show password'}
            aria-pressed={visible}
            onClick={() => setVisible((current) => !current)}
            edge="end"
            size="small"
          >
            {visible ? <EyeSlash size={20} /> : <Eye size={20} />}
          </IconButton>
        </InputAdornment>
      }
    />
  )
}

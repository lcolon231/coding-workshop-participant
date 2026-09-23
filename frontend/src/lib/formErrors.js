/**
 * Map the API's `details[]` onto a form.
 *
 * Each detail is `{ field, message }`. A detail for a known field becomes an
 * inline error under that input; anything else (an unknown field, or the
 * `__root__` sentinel) becomes a form-level message.
 */

/** Make a Pydantic message read like a sentence under an input. */
export function humanise(message) {
  let text = String(message ?? 'Invalid value.').trim()
  text = text.replace(/^Value error,\s*/i, '')
  text = text.charAt(0).toUpperCase() + text.slice(1)
  if (!/[.!?]$/.test(text)) text += '.'
  return text
}

export function splitDetails(details, knownFields) {
  const fieldErrors = {}
  const formErrors = []
  for (const detail of details ?? []) {
    const field = detail?.field
    const message = humanise(detail?.message)
    if (knownFields.includes(field)) {
      // Keep the first message per field: one line under an input is enough.
      if (!fieldErrors[field]) fieldErrors[field] = message
    } else if (field && field !== '__root__') {
      formErrors.push(`${field}: ${message}`)
    } else {
      formErrors.push(message)
    }
  }
  return { fieldErrors, formErrors }
}

/** Move keyboard focus to the first field that has an error, in form order. */
export function focusFirstError(fieldErrors, fieldOrder) {
  const first = fieldOrder.find((name) => fieldErrors[name])
  if (first) document.getElementById(first)?.focus()
}

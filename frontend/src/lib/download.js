/**
 * Hand the browser a file to save. A temporary object URL on an unattached
 * anchor, revoked once the click has been dispatched.
 */
export function saveTextFile(filename, text, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

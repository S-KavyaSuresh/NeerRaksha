export const number = value => new Intl.NumberFormat('en-IN').format(value)
export const timeLabel = minute => `T+${String(Math.floor(minute)).padStart(2, '0')}:${String(Math.floor((minute % 1) * 60)).padStart(2, '0')}`
export function downloadFile(name, content, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  try {
    document.body.appendChild(link)
    link.click()
  } finally {
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }
}

export function normalizeToken(raw) {
  let token = typeof raw === 'string' ? raw.trim() : ''
  while (token.length >= 2 && ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'")))) token = token.slice(1, -1).trim()
  return token
}

export function initializeIon(ion, raw) {
  const token = normalizeToken(raw)
  const diagnostics = { tokenConfigured: Boolean(token), tokenFormatValid: /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token) }
  ion.defaultAccessToken = diagnostics.tokenFormatValid ? token : ''
  return Object.freeze(diagnostics)
}

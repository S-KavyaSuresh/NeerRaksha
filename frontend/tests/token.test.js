import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeToken, initializeIon } from '../src/utils/cesiumToken.js'

test('token normalization handles whitespace and nested accidental wrapping quotes', () => {
  assert.equal(normalizeToken('  " \'abc.def.ghi\' "  '), 'abc.def.ghi')
  assert.equal(normalizeToken(undefined), '')
  assert.equal(normalizeToken('abc.def.ghi'), 'abc.def.ghi')
})

test('ion is assigned before a provider can be created; diagnostics never contain credentials', () => {
  const ion = { defaultAccessToken: 'stale-placeholder' }
  const result = initializeIon(ion, ' "abc.def.ghi" ')
  assert.equal(ion.defaultAccessToken, 'abc.def.ghi')
  assert.deepEqual(result, { tokenConfigured: true, tokenFormatValid: true })
  assert.deepEqual(initializeIon(ion, '<token>'), { tokenConfigured: true, tokenFormatValid: false })
  assert.equal(ion.defaultAccessToken, '')
  assert.deepEqual(initializeIon(ion, ''), { tokenConfigured: false, tokenFormatValid: false })
})

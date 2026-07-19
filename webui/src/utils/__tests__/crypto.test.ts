import { describe, it, expect, vi, beforeEach } from 'vitest'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('crypto', () => {
  it('encrypts and decrypts text roundtrip', async () => {
    const { encryptText, decryptText } = await import('../crypto')
    const plain = 'my-secret-api-key'
    const password = 'test-password'

    const encrypted = await encryptText(plain, password)
    expect(encrypted).not.toBe(plain)
    expect(encrypted.length).toBeGreaterThan(0)

    const decrypted = await decryptText(encrypted, password)
    expect(decrypted).toBe(plain)
  })

  it('fails decrypt with wrong password', async () => {
    const { encryptText, decryptText } = await import('../crypto')
    const encrypted = await encryptText('hello', 'correct')
    await expect(decryptText(encrypted, 'wrong')).rejects.toThrow()
  })

  it('produces different ciphertext for same plaintext', async () => {
    const { encryptText } = await import('../crypto')
    const a = await encryptText('hello', 'pw')
    const b = await encryptText('hello', 'pw')
    expect(a).not.toBe(b)
  })
})

const ITERATIONS = 100000
const KEY_LENGTH = 256

function getEncoder(): TextEncoder {
  return new TextEncoder()
}

function getDecoder(): TextDecoder {
  return new TextDecoder()
}

function generateSalt(): ArrayBuffer {
  const salt = new ArrayBuffer(16)
  new Uint8Array(salt).forEach((_, i, arr) => { arr[i] = Math.floor(Math.random() * 256) })
  return salt
}

async function deriveKey(password: string, salt: ArrayBuffer): Promise<CryptoKey> {
  const enc = getEncoder()
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    enc.encode(password),
    'PBKDF2',
    false,
    ['deriveKey']
  )

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: ITERATIONS,
      hash: 'SHA-256',
    },
    keyMaterial,
    { name: 'AES-GCM', length: KEY_LENGTH },
    false,
    ['encrypt', 'decrypt']
  )
}

export async function encryptText(plainText: string, password: string): Promise<string> {
  const salt = generateSalt()
  const key = await deriveKey(password, salt)
  const iv = crypto.getRandomValues(new Uint8Array(12)) as Uint8Array

  const enc = getEncoder()
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv.buffer as ArrayBuffer },
    key,
    enc.encode(plainText)
  )

  const saltArray = new Uint8Array(salt)
  const combined = new Uint8Array(saltArray.length + iv.length + ciphertext.byteLength)
  combined.set(saltArray, 0)
  combined.set(iv, saltArray.length)
  combined.set(new Uint8Array(ciphertext), saltArray.length + iv.length)

  return btoa(String.fromCharCode(...combined))
}

export async function decryptText(encryptedText: string, password: string): Promise<string> {
  const combined = new Uint8Array(
    atob(encryptedText).split('').map((c) => c.charCodeAt(0))
  )

  const salt = combined.slice(0, 16).buffer as ArrayBuffer
  const iv = combined.slice(16, 28)
  const ciphertext = combined.slice(28)

  const key = await deriveKey(password, salt)

  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv.buffer as ArrayBuffer },
    key,
    ciphertext.buffer as ArrayBuffer
  )

  return getDecoder().decode(plaintext)
}

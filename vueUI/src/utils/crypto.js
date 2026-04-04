/**
 * 使用密码加密文本 (AES-GCM)
 */
export async function encryptText(password, plaintext) {
  try {
    const encoder = new TextEncoder()
    const passwordBuffer = encoder.encode(password)
    
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      passwordBuffer,
      { name: 'PBKDF2' },
      false,
      ['deriveKey']
    )
    
    const salt = crypto.getRandomValues(new Uint8Array(16))
    const iv = crypto.getRandomValues(new Uint8Array(12))
    
    const key = await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt,
        iterations: 100000,
        hash: 'SHA-256'
      },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt']
    )
    
    const plaintextBuffer = encoder.encode(plaintext)
    const encryptedBuffer = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: iv },
      key,
      plaintextBuffer
    )
    
    const combinedBuffer = new Uint8Array(salt.length + iv.length + encryptedBuffer.byteLength)
    combinedBuffer.set(salt, 0)
    combinedBuffer.set(iv, salt.length)
    combinedBuffer.set(new Uint8Array(encryptedBuffer), salt.length + iv.length)
    
    return btoa(String.fromCharCode(...combinedBuffer))
  } catch (error) {
    console.error('加密失败:', error)
    throw new Error('加密失败: ' + error.message)
  }
}

/**
 * 使用密码解密文本
 */
export async function decryptText(password, encryptedBase64) {
  try {
    const combinedBuffer = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0))
    
    const salt = combinedBuffer.slice(0, 16)
    const iv = combinedBuffer.slice(16, 28)
    const encryptedData = combinedBuffer.slice(28)
    
    const encoder = new TextEncoder()
    const passwordBuffer = encoder.encode(password)
    
    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      passwordBuffer,
      { name: 'PBKDF2' },
      false,
      ['deriveKey']
    )
    
    const key = await crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt,
        iterations: 100000,
        hash: 'SHA-256'
      },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['decrypt']
    )
    
    const decryptedBuffer = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv },
      key,
      encryptedData
    )
    
    const decoder = new TextDecoder()
    return decoder.decode(decryptedBuffer)
  } catch (error) {
    console.error('解密失败:', error)
    throw new Error('解密失败: ' + error.message)
  }
}
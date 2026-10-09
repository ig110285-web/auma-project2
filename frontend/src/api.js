/**
 * Тонкая обёртка над fetch: единая обработка ошибок и JSON.
 * credentials: 'include' обязателен — сессия живёт в httpOnly-cookie.
 */

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'include', ...options })

  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const message =
      (isJson && (payload.detail || payload.message)) ||
      (typeof payload === 'string' && payload) ||
      `Ошибка ${response.status}`
    const error = new Error(Array.isArray(message) ? 'Некорректные данные' : message)
    error.status = response.status
    error.payload = payload
    throw error
  }

  return payload
}

export const api = {
  // --- Авторизация ---
  login: (username, password) =>
    request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request('/api/auth/logout', { method: 'POST' }),

  session: () => request('/api/auth/session'),

  changePassword: (currentPassword, newPassword) =>
    request('/api/me/password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),

  // --- Файлы ---
  list: (path = '') => request(`/api/files?path=${encodeURIComponent(path)}`),

  stats: (path = '') => request(`/api/stats?path=${encodeURIComponent(path)}`),

  search: (query, path = '') =>
    request(
      `/api/search?q=${encodeURIComponent(query)}&path=${encodeURIComponent(path)}`,
    ),

  createFolder: (path, name) =>
    request('/api/folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, name }),
    }),

  rename: (path, newName) =>
    request('/api/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, new_name: newName }),
    }),

  move: (path, destination) =>
    request('/api/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, destination }),
    }),

  remove: (paths) =>
    request('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths }),
    }),

  preview: (path) => request(`/api/preview?path=${encodeURIComponent(path)}`),

  downloadUrl: (path) => `/api/download?path=${encodeURIComponent(path)}`,

  // --- Загрузка с прогрессом (XMLHttpRequest даёт событие progress) ---
  upload: (path, files, onProgress) =>
    new Promise((resolve, reject) => {
      const form = new FormData()
      form.append('path', path)
      for (const file of files) form.append('files', file)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/upload')
      xhr.withCredentials = true

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      })

      xhr.addEventListener('load', () => {
        let payload = null
        try {
          payload = JSON.parse(xhr.responseText)
        } catch {
          payload = null
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload)
        } else {
          const detail =
            (payload && (payload.detail || payload.failed?.[0]?.error)) ||
            `Ошибка загрузки ${xhr.status}`
          reject(new Error(Array.isArray(detail) ? 'Некорректный запрос' : detail))
        }
      })

      xhr.addEventListener('error', () => reject(new Error('Сеть недоступна')))
      xhr.send(form)
    }),

  // --- Скачивание архива: POST, поэтому скачиваем через blob ---
  downloadZip: async (paths, filename) => {
    const response = await fetch('/api/download-zip', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths }),
    })
    if (!response.ok) {
      let detail = `Ошибка ${response.status}`
      try {
        detail = (await response.json()).detail || detail
      } catch {
        /* тело не JSON — оставляем общий текст */
      }
      throw new Error(detail)
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'download.zip'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  },
}

export function formatBytes(bytes) {
  if (!bytes) return '0 Б'
  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

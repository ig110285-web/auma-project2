import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, formatBytes, formatDate } from './api.js'

/** Разбирает строку пути в массив сегментов для «хлебных крошек». */
function breadcrumbs(path) {
  const crumbs = [{ label: 'Хранилище', path: '' }]
  if (!path) return crumbs
  const parts = path.split('/').filter(Boolean)
  parts.forEach((part, index) => {
    crumbs.push({ label: part, path: parts.slice(0, index + 1).join('/') })
  })
  return crumbs
}

function fileIcon(entry) {
  if (entry.isDir) return '📁'
  const ext = entry.name.split('.').pop()?.toLowerCase() || ''
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return '🖼️'
  if (['mp4', 'mkv', 'mov', 'avi', 'webm'].includes(ext)) return '🎬'
  if (['mp3', 'wav', 'flac', 'ogg'].includes(ext)) return '🎵'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '🗜️'
  if (['pdf'].includes(ext)) return '📕'
  if (['doc', 'docx', 'txt', 'md', 'rtf'].includes(ext)) return '📄'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'
  if (['js', 'ts', 'jsx', 'tsx', 'py', 'go', 'rs', 'java', 'sh', 'json', 'yml', 'yaml'].includes(ext))
    return '📜'
  return '📦'
}

function isImage(name) {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)
}

function isPdf(name) {
  return name.split('.').pop()?.toLowerCase() === 'pdf'
}

// ---------------------------------------------------------------------------

function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const user = await api.login(username, password)
      onSuccess(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Файловый менеджер</h1>
        <p className="muted">Вход в хранилище</p>

        <label>
          Логин
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>

        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && <div className="alert error">{error}</div>}

        <button type="submit" disabled={busy}>
          {busy ? 'Вход…' : 'Войти'}
        </button>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------

function PreviewModal({ entry, onClose }) {
  const [state, setState] = useState({ loading: true })
  const [textValue, setTextValue] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await api.preview(entry.path)
        if (!cancelled) setState({ loading: false, data })
      } catch (err) {
        if (!cancelled) setState({ loading: false, error: err.message })
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [entry.path])

  useEffect(() => {
    function onKey(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <strong>{entry.name}</strong>
          <div className="row-gap">
            <a className="button ghost" href={api.downloadUrl(entry.path)}>Скачать</a>
            <button className="button ghost" onClick={onClose}>Закрыть</button>
          </div>
        </header>

        <div className="modal-body">
          {state.loading && <p className="muted">Загрузка…</p>}
          {state.error && <div className="alert error">{state.error}</div>}

          {state.data && isImage(entry.name) && (
            <img src={api.downloadUrl(entry.path)} alt={entry.name} className="preview-image" />
          )}

          {state.data && isPdf(entry.name) && (
            <iframe
              title={entry.name}
              src={api.downloadUrl(entry.path)}
              className="preview-frame"
            />
          )}

          {state.data && !isImage(entry.name) && !isPdf(entry.name) && (
            <>
              {state.data.text === null ? (
                <p className="muted">{state.data.reason || 'Предпросмотр недоступен'}</p>
              ) : (
                <>
                  {textValue === null ? (
                    <button
                      className="button"
                      onClick={() => setTextValue(state.data.text)}
                    >
                      Показать текст ({formatBytes(state.data.size)})
                    </button>
                  ) : (
                    <pre className="preview-text">{textValue}</pre>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [path, setPath] = useState('')
  const [listing, setListing] = useState({ entries: [], parent: '' })
  const [stats, setStats] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [uploadProgress, setUploadProgress] = useState(null)
  const [preview, setPreview] = useState(null)
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef(null)

  const notify = useCallback((message) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 3500)
  }, [])

  // Проверяем активную сессию при загрузке страницы.
  useEffect(() => {
    api
      .session()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false))
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [data, usage] = await Promise.all([api.list(path), api.stats('')])
      setListing(data)
      setStats(usage)
      setSelected(new Set())
      setSearchResults(null)
      setQuery('')
    } catch (err) {
      if (err.status === 401) {
        setUser(null)
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    if (user) refresh()
  }, [user, refresh])

  const visibleEntries = useMemo(() => {
    if (searchResults) return searchResults
    return listing.entries
  }, [listing.entries, searchResults])

  // --- Действия ---

  async function handleLogout() {
    await api.logout()
    setUser(null)
    setListing({ entries: [], parent: '' })
  }

  async function handleUpload(fileList) {
    const files = Array.from(fileList || [])
    if (!files.length) return

    setUploadProgress(0)
    setError('')
    try {
      const result = await api.upload(path, files, setUploadProgress)
      const saved = result?.saved?.length || 0
      const failed = result?.failed || []
      if (saved) notify(`Загружено файлов: ${saved}`)
      if (failed.length) setError(failed.map((f) => `${f.name}: ${f.error}`).join('; '))
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploadProgress(null)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function handleNewFolder() {
    const name = window.prompt('Имя новой папки:')
    if (!name) return
    try {
      await api.createFolder(path, name)
      notify('Папка создана')
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRename(entry) {
    const name = window.prompt('Новое имя:', entry.name)
    if (!name || name === entry.name) return
    try {
      await api.rename(entry.path, name)
      notify('Переименовано')
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleMove(entry) {
    const destination = window.prompt(
      'Куда переместить (путь от корня, пусто = корень):',
      listing.parent,
    )
    if (destination === null) return
    try {
      await api.move(entry.path, destination)
      notify('Перемещено')
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(entries) {
    const list = Array.from(entries)
    if (!list.length) return
    const label = list.length === 1 ? `«${list[0].name}»` : `${list.length} объектов`
    if (!window.confirm(`Удалить ${label}? Действие необратимо.`)) return
    try {
      const result = await api.remove(list.map((item) => item.path))
      if (result.failed) {
        setError(result.results.filter((r) => !r.ok).map((r) => `${r.path}: ${r.error}`).join('; '))
      }
      notify(`Удалено: ${result.deleted}`)
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDownloadZip(entries) {
    const list = Array.from(entries)
    if (!list.length) return
    try {
      const name = list.length === 1 ? `${list[0].name}.zip` : 'selection.zip'
      await api.downloadZip(list.map((item) => item.path), name)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSearch(event) {
    event.preventDefault()
    if (!query.trim()) {
      setSearchResults(null)
      return
    }
    try {
      const data = await api.search(query.trim(), path)
      setSearchResults(data.results)
      if (!data.results.length) notify('Ничего не найдено')
    } catch (err) {
      setError(err.message)
    }
  }

  function toggleSelect(entry) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(entry.path)) next.delete(entry.path)
      else next.add(entry.path)
      return next
    })
  }

  function toggleAll() {
    setSelected((current) => {
      if (current.size === visibleEntries.length) return new Set()
      return new Set(visibleEntries.map((entry) => entry.path))
    })
  }

  function openEntry(entry) {
    if (entry.isDir) {
      setPath(entry.path)
    } else {
      setPreview(entry)
    }
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    handleUpload(event.dataTransfer.files)
  }

  const selectedEntries = visibleEntries.filter((entry) => selected.has(entry.path))
  const allSelected = visibleEntries.length > 0 && selected.size === visibleEntries.length

  if (checking) {
    return <div className="centered"><p className="muted">Загрузка…</p></div>
  }

  if (!user) {
    return <LoginScreen onSuccess={setUser} />
  }

  return (
    <div
      className={`app ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <header className="topbar">
        <div className="brand">
          <span className="logo">🗂️</span>
          <div>
            <strong>Файловый менеджер</strong>
            <div className="muted small">
              {stats
                ? `${formatBytes(stats.total_bytes)} · файлов: ${stats.file_count}`
                : '—'}
            </div>
          </div>
        </div>

        <form className="search" onSubmit={handleSearch}>
          <input
            placeholder="Поиск по имени…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" className="button ghost">Найти</button>
          {searchResults && (
            <button
              type="button"
              className="button ghost"
              onClick={() => {
                setSearchResults(null)
                setQuery('')
              }}
            >
              Сброс
            </button>
          )}
        </form>

        <div className="user-box">
          <span className="muted small">{user.username}</span>
          <button className="button ghost" onClick={handleLogout}>Выйти</button>
        </div>
      </header>

      <nav className="breadcrumbs">
        {breadcrumbs(path).map((crumb, index, all) => (
          <span key={crumb.path || 'root'}>
            <button
              className="link"
              onClick={() => setPath(crumb.path)}
              disabled={index === all.length - 1 && !searchResults}
            >
              {crumb.label}
            </button>
            {index < all.length - 1 && <span className="sep">/</span>}
          </span>
        ))}
      </nav>

      {uploadsBar(uploadProgress)}

      {error && (
        <div className="alert error dismissible">
          <span>{error}</span>
          <button className="link" onClick={() => setError('')}>✕</button>
        </div>
      )}
      {notice && <div className="alert info">{notice}</div>}

      <section className="toolbar">
        <button className="button" onClick={() => fileInput.current?.click()}>
          ⬆ Загрузить
        </button>
        <button className="button ghost" onClick={handleNewFolder}>📁 Новая папка</button>

        {selectedEntries.length > 0 && (
          <>
            <span className="divider" />
            <span className="muted small">Выбрано: {selectedEntries.length}</span>
            {selectedEntries.length === 1 && (
              <>
                <button className="button ghost" onClick={() => handleRename(selectedEntries[0])}>
                  ✏️ Переименовать
                </button>
                <button className="button ghost" onClick={() => handleMove(selectedEntries[0])}>
                  ↔️ Переместить
                </button>
              </>
            )}
            <button className="button ghost" onClick={() => handleDownloadZip(selectedEntries)}>
              🗜️ Скачать ZIP
            </button>
            <button className="button danger" onClick={() => handleDelete(selectedEntries)}>
              🗑️ Удалить
            </button>
          </>
        )}

        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          onChange={(event) => handleUpload(event.target.files)}
        />
      </section>

      {searchResults && (
        <div className="alert info">
          Результаты поиска: {searchResults.length}
        </div>
      )}

      <main className="content">
        {loading && <p className="muted">Загрузка…</p>}

        {!loading && visibleEntries.length === 0 && (
          <div className="empty">
            <p>Пусто</p>
            <p className="muted small">
              Перетащите файлы в окно или нажмите «Загрузить»
            </p>
          </div>
        )}

        {!loading && visibleEntries.length > 0 && (
          <table className="files">
            <thead>
              <tr>
                <th className="check">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>
                <th>Имя</th>
                <th className="size">Размер</th>
                <th className="date">Изменён</th>
                <th className="actions">Действия</th>
              </tr>
            </thead>
            <tbody>
              {path && !searchResults && (
                <tr className="row">
                  <td />
                  <td colSpan={4}>
                    <button
                      className="link"
                      onClick={() => setPath(listing.parent || '')}
                    >
                      ⬅ .. наверх
                    </button>
                  </td>
                </tr>
              )}

              {visibleEntries.map((entry) => (
                <tr
                  key={entry.path}
                  className={selected.has(entry.path) ? 'row selected' : 'row'}
                >
                  <td className="check">
                    <input
                      type="checkbox"
                      checked={selected.has(entry.path)}
                      onChange={() => toggleSelect(entry)}
                    />
                  </td>
                  <td>
                    <button className="entry-name" onClick={() => openEntry(entry)}>
                      <span className="icon">{fileIcon(entry)}</span>
                      <span>{entry.name}</span>
                    </button>
                    {searchResults && (
                      <div className="muted small">{entry.path}</div>
                    )}
                  </td>
                  <td className="size muted">
                    {entry.is_dir ? '—' : formatBytes(entry.size)}
                  </td>
                  <td className="date muted">{formatDate(entry.modified)}</td>
                  <td className="actions">
                    {!entry.isDir && (
                      <a className="link" href={api.downloadUrl(entry.path)}>Скачать</a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>

      {preview && <PreviewModal entry={preview} onClose={() => setPreview(null)} />}

      {dragging && <div className="drop-overlay">Отпустите файлы для загрузки</div>}
    </div>
  )
}

function uploadsBar(progress) {
  if (progress === null) return null
  return (
    <div className="upload-bar">
      <div className="upload-fill" style={{ width: `${progress}%` }} />
      <span className="upload-label">Загрузка… {progress}%</span>
    </div>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, formatBytes, formatDate } from './api.js'

/** Разбирает строку пути в массив сегментов для «хлебных крошек». */
function breadcrumbs(path) {
  const crumbs = [{ label: 'Все файлы', path: '' }]
  if (!path) return crumbs
  const parts = path.split('/').filter(Boolean)
  parts.forEach((part, index) => {
    crumbs.push({ label: part, path: parts.slice(0, index + 1).join('/') })
  })
  return crumbs
}

/** Иконка для строки таблицы. */
function fileIcon(entry) {
  if (entry.isDir) return '📁'
  const ext = entry.name.split('.').pop()?.toLowerCase() || ''
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return '🖼️'
  if (['mp4', 'mkv', 'mov', 'avi', 'webm'].includes(ext)) return '🎬'
  if (['mp3', 'wav', 'flac', 'ogg'].includes(ext)) return '🎵'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '🗜️'
  if (ext === 'pdf') return '📕'
  if (['doc', 'docx', 'txt', 'md', 'rtf'].includes(ext)) return '📄'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'
  if (['js', 'ts', 'jsx', 'tsx', 'py', 'go', 'rs', 'java', 'sh', 'json', 'yml', 'yaml'].includes(ext))
    return '📜'
  return '📦'
}

/** Короткое расширение файла для подписи под именем. */
function fileKind(entry) {
  if (entry.isDir) return 'Папка'
  const ext = entry.name.split('.').pop()?.toLowerCase() || ''
  if (!ext || ext === entry.name.toLowerCase()) return 'Файл'
  return ext.toUpperCase()
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
        <div className="login-logo">A</div>
        <h1>Файловый менеджер</h1>
        <p className="subtitle">Войдите, чтобы работать с файлами</p>

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

        {error && <div className="alert error"><span className="alert-text">{error}</span></div>}

        <button type="submit" className="button" disabled={busy}>
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
          <span className="modal-title">{entry.name}</span>
          <div className="row-gap">
            <a className="button ghost" href={api.downloadUrl(entry.path)}>Скачать</a>
            <button className="button ghost" onClick={onClose}>Закрыть</button>
          </div>
        </header>

        <div className="modal-body">
          {state.loading && <p className="muted">Загрузка…</p>}
          {state.error && <div className="alert error"><span className="alert-text">{state.error}</span></div>}

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
              ) : textValue === null ? (
                <button className="button" onClick={() => setTextValue(state.data.text)}>
                  Показать текст ({formatBytes(state.data.size)})
                </button>
              ) : (
                <pre className="preview-text">{textValue}</pre>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

const NAV_ITEMS = [
  { key: 'files', label: 'Мои файлы', icon: '🏠' },
  { key: 'recent', label: 'Недавние', icon: '🕐' },
  { key: 'shared', label: 'Общие', icon: '👥' },
  { key: 'starred', label: 'Избранное', icon: '⭐' },
]

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
  const [showPromo, setShowPromo] = useState(true)
  const [sort, setSort] = useState({ by: 'name', asc: true })
  const fileInput = useRef(null)

  const notify = useCallback((message) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 3500)
  }, [])

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
      if (err.status === 401) setUser(null)
      else setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    if (user) refresh()
  }, [user, refresh])

  const visibleEntries = useMemo(() => {
    const source = searchResults ?? listing.entries
    const sorted = [...source].sort((a, b) => {
      // Папки всегда идут первыми, независимо от выбранной сортировки.
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      let result = 0
      if (sort.by === 'size') result = a.size - b.size
      else if (sort.by === 'modified')
        result = new Date(a.modified) - new Date(b.modified)
      else result = a.name.localeCompare(b.name, 'ru')
      return sort.asc ? result : -result
    })
    return sorted
  }, [listing.entries, searchResults, sort])

  const totalLabel = useMemo(() => {
    if (searchResults) return `${searchResults.length} найдено`
    return `${visibleEntries.length} всего`
  }, [searchResults, visibleEntries.length])

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
        setError(
          result.results
            .filter((r) => !r.ok)
            .map((r) => `${r.path}: ${r.error}`)
            .join('; '),
        )
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

  function toggleSort(by) {
    setSort((current) =>
      current.by === by ? { by, asc: !current.asc } : { by, asc: true },
    )
  }

  function openEntry(entry) {
    if (entry.isDir) setPath(entry.path)
    else setPreview(entry)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    handleUpload(event.dataTransfer.files)
  }

  const selectedEntries = visibleEntries.filter((entry) => selected.has(entry.path))
  const allSelected = visibleEntries.length > 0 && selected.size === visibleEntries.length
  const rootName = path ? path.split('/').pop() : 'Мои файлы и материалы'

  if (checking) {
    return <div className="centered"><p className="muted">Загрузка…</p></div>
  }

  if (!user) {
    return <LoginScreen onSuccess={setUser} />
  }

  return (
    <div
      className="app"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      {/* --- Сайдбар --- */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">A</div>
          <span className="brand-name">auma</span>
        </div>

        <div className="sidebar-search">
          <span className="search-icon">🔍</span>
          <input
            placeholder="Поиск…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') handleSearch(event)
            }}
          />
        </div>

        <nav className="nav">
          {NAV_ITEMS.map((item, index) => (
            <button
              key={item.key}
              className={index === 0 ? 'nav-item active' : 'nav-item'}
              onClick={() => {
                if (index === 0) {
                  setPath('')
                  setSearchResults(null)
                } else {
                  notify('Раздел появится позже')
                }
              }}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
              {index === 0 && stats && (
                <span className="nav-count">{stats.file_count}</span>
              )}
            </button>
          ))}
        </nav>

        {showPromo && (
          <div className="sidebar-promo">
            <button className="promo-close" onClick={() => setShowPromo(false)}>✕</button>
            <div className="promo-icon">⚠️</div>
            <div className="promo-text">
              {stats
                ? `Занято ${formatBytes(stats.total_bytes)} из ${stats.quota_bytes ? formatBytes(stats.quota_bytes) : '∞'}`
                : 'Загрузка статистики…'}
            </div>
            <div className="promo-actions">
              <span className="link" onClick={() => setShowPromo(false)}>Скрыть</span>
              <span className="link" onClick={handleNewFolder}>Создать папку</span>
            </div>
          </div>
        )}

        <div className="user-card">
          <div className="avatar">{user.username.slice(0, 2).toUpperCase()}</div>
          <div className="user-meta">
            <div className="user-name">{user.username}</div>
            <div className="user-role">{user.is_admin ? 'Администратор' : 'Пользователь'}</div>
          </div>
          <button className="logout-button" onClick={handleLogout} title="Выйти">
            ⎋
          </button>
        </div>
      </aside>

      {/* --- Основная область --- */}
      <div className="main">
        <div className="main-header">
          <button
            className="back-link"
            onClick={() => setPath(listing.parent || '')}
            disabled={!path}
          >
            ‹ {path ? 'Наверх' : 'Все проекты'}
          </button>

          <div className="title-row">
            <h1 className="page-title">{rootName}</h1>
            <div className="title-actions">
              <button className="button ghost" onClick={() => handleDownloadZip(selectedEntries)} disabled={!selectedEntries.length}>
                Скачать ZIP
              </button>
              <button className="button" onClick={() => fileInput.current?.click()}>
                + Загрузить файл
              </button>
            </div>
          </div>
        </div>

        <div className="main-content">
          {uploadProgress !== null && (
            <div className="upload-bar">
              <div className="upload-fill" style={{ width: `${uploadProgress}%` }} />
              <span className="upload-label">Загрузка… {uploadProgress}%</span>
            </div>
          )}

          {error && (
            <div className="alert error">
              <span className="alert-text">{error}</span>
              <button className="alert-close" onClick={() => setError('')}>✕</button>
            </div>
          )}
          {notice && <div className="alert success"><span className="alert-text">{notice}</span></div>}

          {!path && !searchResults && (
            <div
              className={dragging ? 'dropzone active' : 'dropzone'}
              onClick={() => fileInput.current?.click()}
            >
              <div className="dropzone-icon">⬆</div>
              <div className="dropzone-main">
                <span className="link">Нажмите здесь</span> или перетащите файлы
              </div>
              <div className="dropzone-hint">
                Максимум {stats ? formatBytes(stats.max_upload_bytes) : '2 ГБ'} на файл
              </div>
              <div className="dropzone-art">📄</div>
            </div>
          )}

          <section className="panel">
            <header className="panel-header">
              <div className="panel-title-block">
                <div className="panel-title">
                  Файлы
                  <span className="total-badge">{totalLabel}</span>
                </div>
                <div className="panel-subtitle">
                  Здесь ваши загруженные файлы и папки
                </div>
              </div>

              <div className="panel-tools">
                <form className="search-box" onSubmit={handleSearch}>
                  <input
                    placeholder="Поиск…"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  <button type="submit" className="search-submit" title="Найти">🔍</button>
                </form>

                {selectedEntries.length > 0 && (
                  <>
                    <span className="muted small">{selectedEntries.length} выбрано</span>
                    {selectedEntries.length === 1 && (
                      <>
                        <button className="button soft" onClick={() => handleRename(selectedEntries[0])}>
                          Изменить
                        </button>
                        <button className="button soft" onClick={() => handleMove(selectedEntries[0])}>
                          Переместить
                        </button>
                      </>
                    )}
                    <button className="button danger" onClick={() => handleDelete(selectedEntries)}>
                      Удалить
                    </button>
                  </>
                )}

                <button className="button ghost" onClick={handleNewFolder}>+ Папка</button>
              </div>
            </header>

            {searchResults && (
              <div style={{ padding: '12px 20px 0' }}>
                <div className="alert info">
                  <span className="alert-text">Результаты поиска по запросу «{query}»</span>
                  <button
                    className="alert-close"
                    onClick={() => {
                      setSearchResults(null)
                      setQuery('')
                    }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            {loading ? (
              <div className="empty"><p className="muted">Загрузка…</p></div>
            ) : visibleEntries.length === 0 ? (
              <div className="empty">
                <div className="empty-icon">📂</div>
                <p><strong>Пока пусто</strong></p>
                <p className="muted small">
                  Перетащите файлы в окно или нажмите «Загрузить файл»
                </p>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="files">
                  <thead>
                    <tr>
                      <th className="check">
                        <input
                          type="checkbox"
                          checked={allSelected}
                          onChange={toggleAll}
                          title="Выбрать все"
                        />
                      </th>
                      <th className="sortable" onClick={() => toggleSort('name')}>
                        Имя файла
                        <span className="sort-arrows">▲<br />▼</span>
                      </th>
                      <th className="col-size sortable" onClick={() => toggleSort('size')}>
                        Размер
                        <span className="sort-arrows">▲<br />▼</span>
                      </th>
                      <th className="col-date sortable" onClick={() => toggleSort('modified')}>
                        Изменён
                        <span className="sort-arrows">▲<br />▼</span>
                      </th>
                      <th>Владелец</th>
                      <th className="col-actions">Действия</th>
                    </tr>
                  </thead>

                  <tbody>
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
                          <div className="name-cell">
                            <div className={entry.isDir ? 'file-thumb dir' : 'file-thumb'}>
                              {fileIcon(entry)}
                            </div>
                            <div className="name-block">
                              <button className="entry-name" onClick={() => openEntry(entry)}>
                                {entry.name}
                              </button>
                              <div className="entry-meta">
                                {searchResults ? entry.path : fileKind(entry)}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="col-size muted">
                          {entry.isDir ? '—' : formatBytes(entry.size)}
                        </td>

                        <td className="col-date muted">{formatDate(entry.modified)}</td>

                        <td>
                          <div className="user-cell">
                            <div className="user-avatar-sm">
                              {user.username.slice(0, 2).toUpperCase()}
                            </div>
                            <div className="user-cell-meta">
                              <div className="user-cell-name">{user.username}</div>
                              <div className="user-cell-mail">
                                {user.is_admin ? 'Администратор' : 'Пользователь'}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="col-actions">
                          <div className="row-actions">
                            <span className="link danger" onClick={() => handleDelete([entry])}>
                              Удалить
                            </span>
                            <span className="link" onClick={() => handleRename(entry)}>
                              Изменить
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>

      <input
        ref={fileInput}
        type="file"
        multiple
        hidden
        onChange={(event) => handleUpload(event.target.files)}
      />

      {preview && <PreviewModal entry={preview} onClose={() => setPreview(null)} />}

      {dragging && <div className="drop-overlay">Отпустите файлы для загрузки</div>}
    </div>
  )
}

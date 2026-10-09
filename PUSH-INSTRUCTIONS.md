# Как залить проект на GitHub

Репозиторий: https://github.com/ig110285-web/auma-project2

Локальный git-репозиторий уже создан, коммит сделан, `origin` прописан.
Осталось выполнить **одну команду** в обычном терминале (вне песочницы).

## Шаг 1. Откройте терминал

Подойдёт PowerShell, Windows Terminal или Git Bash — любой, где доступен `git`.

## Шаг 2. Перейдите в каталог проекта

```powershell
cd C:\Users\oilsy\Documents\deepseek-harness\default-workspace
```

## Шаг 3. Проверьте, что всё на месте

```powershell
git log --oneline -1
git remote -v
```

Ожидаемый вывод:

```
db7c487 Файловый менеджер: FastAPI + React + Docker
origin  git@github.com:ig110285-web/auma-project2.git (fetch)
origin  git@github.com:ig110285-web/auma-project2.git (push)
```

## Шаг 4. Выполните push

```powershell
git push -u origin main
```

При первом подключении Git спросит подтверждение отпечатка хоста:

```
The authenticity of host 'github.com (140.82.121.4)' can't be established.
ED25519 key fingerprint is SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Напишите `yes` и нажмите Enter. Отпечаток `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`
— это официальный ключ GitHub, его можно сверить на
https://docs.github.com/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints

## Если возникнет ошибка

### `Permission denied (publickey)`

Ключ не подхватился. Проверьте:

```powershell
ssh -T git@github.com
```

Должно ответить `Hi ig110285-web! You've successfully authenticated`.
Если нет — убедитесь, что ключ `~/.ssh/id_ed25519` добавлен в
https://github.com/settings/keys

### `Host key verification failed`

Добавьте GitHub в известные хосты:

```powershell
ssh-keyscan github.com >> $env:USERPROFILE\.ssh\known_hosts
```

### `failed to push some refs` / `non-fast-forward`

В удалённом репозитории уже есть коммиты. Посмотрите, что там:

```powershell
git fetch origin
git log --oneline origin/main
```

Если те коммиты не нужны — перезапишите историю:

```powershell
git push -u origin main --force
```

⚠️ `--force` удаляет удалённую историю безвозвратно. Применяйте, только если
уверены, что в репозитории нет ничего ценного.

### `src refspec main does not match any`

Коммит не создан. Проверьте `git log` и при необходимости создайте коммит:

```powershell
git add -A
git commit -m "Файловый менеджер: FastAPI + React + Docker"
```

### Git долго висит и ничего не происходит

Возможно, SSH-ключ защищён паролем и запрашивает ввод, который не виден.
Проверьте:

```powershell
ssh-add -l
```

Если ключа нет в списке — добавьте: `ssh-add $env:USERPROFILE\.ssh\id_ed25519`

## Шаг 5. Проверка результата

Откройте https://github.com/ig110285-web/auma-project2 — файлы должны
появиться в ветке `main`.

---

## После успешного push: запуск проекта

```powershell
# Создать конфигурацию
Copy-Item .env.example .env

# Открыть .env в блокноте и задать:
#   ADMIN_PASSWORD — пароль для входа
#   SECRET_KEY     — случайная строка (можно получить: openssl rand -hex 32)
notepad .env

# Запустить
docker compose up -d --build

# Открыть в браузере
start http://localhost:8080
```

Логин — значение `ADMIN_USERNAME` (по умолчанию `admin`), пароль — тот,
что вы указали в `ADMIN_PASSWORD`.

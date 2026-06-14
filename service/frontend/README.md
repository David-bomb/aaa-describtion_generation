# Avito Qwen Frontend

Vite + React + TypeScript интерфейс для локального сервиса генерации описаний товаров. UI вдохновлён рабочими экранами Авито: загрузка фото, поля объявления, JSON-параметры, статус модели, генерация и копирование результата.

## Docker Compose

Обычный запуск из корня проекта:

```powershell
docker compose up --build
```

Frontend будет доступен на:

```text
http://localhost:5173
```

В Docker-режиме Vite собирается в статические файлы, nginx отдаёт UI и проксирует `/health`, `/ready`, `/generate-description` на внутренний `api:8080`.

Порт можно изменить через `FRONTEND_PORT` в корневом `.env`.

## Dev-Запуск

Из корня проекта:

```powershell
cmd /c npm --prefix frontend install
cmd /c npm --prefix frontend run dev
```

Если npm не может писать в системный cache:

```powershell
cmd /c npm --prefix frontend install --cache E:\AAA\proj\service\.npm-cache
```

Открыть:

```text
http://localhost:5173
```

## Backend Proxy

В dev-режиме Vite проксирует эти пути на `http://localhost:8081`:

- `/health`
- `/ready`
- `/generate-description`

Поэтому CORS на FastAPI не нужен.

В Docker-режиме те же пути проксирует nginx из `frontend/nginx.conf`.

## API Override

Для прямого обращения к другому API создай `frontend/.env.local`:

```text
VITE_API_BASE_URL=http://localhost:8081
```

Пустое значение означает same-origin запросы через Vite proxy.

## Команды

```powershell
cmd /c npm --prefix frontend run test
cmd /c npm --prefix frontend run build
cmd /c npm --prefix frontend run preview
cmd /c npm --prefix frontend audit --json
```

## Проверено

- Unit/UI tests: `6 passed`.
- Production build: ok.
- npm audit: `0 vulnerabilities`.

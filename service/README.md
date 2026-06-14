# Avito Qwen Description Service

Локальный сервис для генерации описаний товаров на русском языке по фотографии, названию, категории и параметрам товара. Система поднимается через Docker Compose одной командой и включает frontend, FastAPI API и vLLM runtime с моделью `Qwen/Qwen3-VL-4B-Instruct`.

## Состав сервисов

| Сервис | Назначение | Порт снаружи | Внутренний порт |
|---|---|---:|---:|
| `frontend` | React-интерфейс, nginx static server и proxy к API | `5173` | `80` |
| `api` | FastAPI backend, валидация входных данных, сбор prompt, запрос к vLLM | `8081` | `8080` |
| `qwen-vllm` | OpenAI-compatible vLLM server с Qwen VL model | `8000` | `8000` |

Frontend проксирует `/health`, `/ready` и `/generate-description` во внутренний `api:8080`. Backend обращается к vLLM по внутреннему адресу `http://qwen-vllm:8000/v1`.

## Стек

- Python 3.11, FastAPI, Uvicorn, OpenAI-compatible client.
- vLLM с моделью `Qwen/Qwen3-VL-4B-Instruct`.
- 4-bit runtime через `bitsandbytes`: `--quantization bitsandbytes`, `--load-format bitsandbytes`, `--dtype float16`.
- React, TypeScript, Vite, nginx.
- Docker Compose.
- NVIDIA GPU через Docker GPU support.

Текущий 4-bit режим является `bitsandbytes 4-bit` для инференса. Это не отдельный strict `GPTQ/AWQ/W4A16 INT4` checkpoint.

## Структура проекта

```text
service/
  app/                         FastAPI-приложение
    main.py                    HTTP endpoints
    qwen_client.py             клиент к vLLM
    prompt.py                  prompt template для Авито-описаний
    schemas.py                 Pydantic-схемы
    settings.py                настройки из env
  frontend/                    Vite + React frontend
    src/                       UI, API client, tests
    Dockerfile                 production build frontend
    nginx.conf                 static server и proxy к API
  scripts/
    evaluate_products.py       проверка на реальном датасете
    load_test.py               нагрузочный тест
    smoke_request.ps1          быстрый multipart-запрос к API
  tests/                       backend unit tests
  docker-compose.yml           общий запуск frontend + API + vLLM
  Dockerfile                   образ API
  requirements.txt             runtime зависимости API
  requirements-dev.txt         dev/test зависимости
  .env.example                 пример переменных окружения
```

Данные, веса моделей, отчёты, виртуальные окружения, `node_modules` и frontend build artifacts не должны попадать в git. Эти пути закрыты в `.gitignore`.

## Требования

- Windows с Docker Desktop или Linux с Docker Engine.
- NVIDIA GPU с поддержкой запуска контейнеров.
- NVIDIA Container Toolkit / включённый GPU support в Docker Desktop.
- Свободное место для весов модели Hugging Face.
- Рекомендуемая видеокарта: RTX 3060 12 GB или лучше.
- Для локальной разработки без Docker: Python 3.11/3.12 и Node.js 22 LTS.

## Настройка

Создайте `.env` из примера, если нужно изменить порты или параметры runtime:

```powershell
Copy-Item .env.example .env
```

Основные переменные:

```text
APP_PORT=8081
FRONTEND_PORT=5173
QWEN_MODEL_ID=Qwen/Qwen3-VL-4B-Instruct
QWEN_OPENAI_BASE_URL=http://qwen-vllm:8000/v1
VLLM_MAX_MODEL_LEN=2048
VLLM_GPU_MEMORY_UTILIZATION=0.90
GENERATION_MAX_TOKENS=180
GENERATION_TEMPERATURE=0.2
GENERATION_TOP_P=0.9
```

По умолчанию `.env` не обязателен: Docker Compose возьмёт рабочие значения из `docker-compose.yml` и `.env.example`.

## Сборка и запуск

Из корня проекта:

```powershell
docker compose up --build
```

Первый запуск может занять заметное время, потому что vLLM скачивает веса `Qwen/Qwen3-VL-4B-Instruct` в Docker volume `hf-cache`.

После запуска доступны:

```text
Frontend: http://localhost:5173
API:      http://localhost:8081
vLLM:     http://localhost:8000
```

## Проверка запуска

Проверить API:

```powershell
curl.exe http://localhost:8081/health
curl.exe http://localhost:8081/ready
```

Ожидаемый ответ `/health`:

```json
{"status":"ok"}
```

Ожидаемый ответ `/ready`, когда модель загружена:

```json
{"ready":true}
```

Проверить vLLM:

```powershell
curl.exe http://localhost:8000/v1/models
```

Проверить frontend proxy:

```powershell
curl.exe http://localhost:5173/health
curl.exe http://localhost:5173/ready
```

## Использование через frontend

Откройте:

```text
http://localhost:5173
```

В интерфейсе нужно загрузить изображение товара, заполнить `title`, `category_name` и при необходимости JSON `params`. Frontend отправляет multipart-запрос в API и показывает готовое описание с кнопкой копирования.

## Использование через API

Endpoint:

```text
POST /generate-description
```

Формат запроса: `multipart/form-data`.

Поля:

- `image` - изображение товара, JPEG/PNG/WEBP;
- `title` - заголовок объявления;
- `category_name` - категория;
- `params` - JSON-объект с характеристиками.

Пример smoke-запроса:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\smoke_request.ps1 `
  -ImagePath .\data\smoke-phone.png `
  -Title "iPhone 13 128 ГБ" `
  -CategoryName "Электроника" `
  -ParamsJson '{"состояние":"б/у","память":"128 ГБ","цвет":"синий"}'
```

Пример ответа:

```json
{
  "description": "Смартфон Apple iPhone 13 с памятью 128 ГБ, состояние б/у. Корпус синего цвета."
}
```

## Остановка

Остановить контейнеры:

```powershell
docker compose stop
```

Остановить и удалить контейнеры вместе с compose network:

```powershell
docker compose down
```

Кэш Hugging Face в volume сохранится. Чтобы удалить и его, используйте `docker compose down -v`.

## Локальная разработка

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend dev server:

```powershell
cmd /c npm --prefix frontend install
cmd /c npm --prefix frontend run dev
```

Frontend build и tests:

```powershell
cmd /c npm --prefix frontend run build
cmd /c npm --prefix frontend run test
```

В dev-режиме Vite проксирует `/health`, `/ready` и `/generate-description` на `http://localhost:8081`.

## Проверка на датасете

Ожидаемая структура данных:

```text
data/
  valid_with_params.csv
  AAA_1image_dataset_images/
    <image_id>.jpg
```

CSV должен содержать колонки:

- `image_id`
- `title`
- `category_name`
- `params`

Прогон evaluator на 20 товарах:

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_products.py `
  --csv .\data\valid_with_params.csv `
  --images-dir .\data\AAA_1image_dataset_images `
  --url http://localhost:8081/generate-description `
  --limit 20 `
  --seed 42
```

Отчёт пишется в `reports/*.jsonl` и содержит описание, latency, статус запроса, ошибки и GPU peak metrics.

## Нагрузочное тестирование

Пример основного прогона:

```powershell
.\.venv\Scripts\python.exe .\scripts\load_test.py `
  --concurrency-levels 1,2,4,8,16 `
  --requests-per-level 16 `
  --warmup-requests 2 `
  --timeout 300 `
  --output .\reports\load_test_main.jsonl
```

Скрипт измеряет latency, throughput, число успешных и ошибочных запросов, GPU utilization, VRAM, power и Docker stats.

По последним замерам сервис стабильно обрабатывал параллельность до 64 запросов без ошибок при большом timeout, но практический рабочий диапазон для интерактивного использования сейчас `2-4` одновременных запроса. Причина - vLLM запущен с `--max-num-seqs 1`, поэтому лишние запросы ждут очередь.

## Частые проблемы

Если `/ready` возвращает `false`, модель ещё загружается или vLLM не стартовал. Проверьте логи:

```powershell
docker compose logs --tail 200 qwen-vllm
```

Если Docker не видит GPU, проверьте NVIDIA driver, Docker Desktop GPU support и доступность команды:

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Если npm не может писать в системный cache, используйте локальный cache:

```powershell
cmd /c npm --prefix frontend install --cache E:\AAA\proj\service\.npm-cache
```

Если при высокой параллельности растёт latency, это ожидаемо для текущей конфигурации vLLM. Для увеличения throughput нужно отдельно подбирать `max-num-seqs`, лимиты памяти и параметры batching.

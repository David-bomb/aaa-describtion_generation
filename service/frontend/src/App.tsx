import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Copy,
  FileImage,
  Loader2,
  RefreshCw,
  Send,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, fetchReady, generateDescription } from "./api";

type ReadyState = "checking" | "ready" | "not_ready" | "error";

type ParsedParams =
  | { ok: true; value: Record<string, unknown>; message: "" }
  | { ok: false; value: null; message: string };

const DEFAULT_PARAMS = "{}";
const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function parseParamsText(paramsText: string): ParsedParams {
  const trimmed = paramsText.trim();
  if (!trimmed) {
    return { ok: true, value: {}, message: "" };
  }

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      return { ok: false, value: null, message: "Параметры должны быть JSON-объектом." };
    }
    return { ok: true, value: parsed as Record<string, unknown>, message: "" };
  } catch {
    return { ok: false, value: null, message: "Параметры должны быть валидным JSON." };
  }
}

function App() {
  const [title, setTitle] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [paramsText, setParamsText] = useState(DEFAULT_PARAMS);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [readyState, setReadyState] = useState<ReadyState>("checking");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const parsedParams = useMemo(() => parseParamsText(paramsText), [paramsText]);
  const canSubmit = Boolean(
    imageFile && title.trim() && categoryName.trim() && parsedParams.ok && !isSubmitting,
  );

  const refreshReady = useCallback(async () => {
    setReadyState("checking");
    try {
      const ready = await fetchReady();
      setReadyState(ready ? "ready" : "not_ready");
    } catch {
      setReadyState("error");
    }
  }, []);

  useEffect(() => {
    void refreshReady();
  }, [refreshReady]);

  useEffect(() => {
    if (!imageFile) {
      setPreviewUrl(null);
      return;
    }

    const objectUrl = URL.createObjectURL(imageFile);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [imageFile]);

  const setImage = (file: File | undefined) => {
    if (!file) {
      return;
    }
    if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
      setError("Загрузи JPEG, PNG или WEBP.");
      return;
    }

    setImageFile(file);
    setDescription("");
    setError("");
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    setImage(event.dataTransfer.files[0]);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!imageFile || !parsedParams.ok) {
      return;
    }

    setIsSubmitting(true);
    setError("");
    setDescription("");
    setIsCopied(false);

    try {
      const result = await generateDescription({
        image: imageFile,
        title: title.trim(),
        categoryName: categoryName.trim(),
        params: parsedParams.value,
      });
      setDescription(result.description);
      void refreshReady();
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setError(requestError.message);
      } else {
        setError("Не удалось сгенерировать описание.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const copyDescription = async () => {
    if (!description) {
      return;
    }

    await navigator.clipboard.writeText(description);
    setIsCopied(true);
    window.setTimeout(() => setIsCopied(false), 1600);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">
          <span className="brand-dot brand-dot-blue" />
          <span className="brand-dot brand-dot-green" />
          <span className="brand-dot brand-dot-red" />
        </div>
        <div className="topbar-title">
          <h1>Генератор описаний</h1>
          <p>Qwen3-VL, 4-bit bitsandbytes</p>
        </div>
        <div className={`ready-pill ready-pill-${readyState}`}>
          {readyIcon(readyState)}
          <span>{readyLabel(readyState)}</span>
          <button
            className="icon-button"
            type="button"
            title="Обновить статус"
            aria-label="Обновить статус"
            onClick={refreshReady}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      <section className="workspace" aria-label="Генерация описания товара">
        <form className="workspace-panel input-panel" onSubmit={handleSubmit}>
          <div className="panel-heading">
            <FileImage size={20} />
            <h2>Данные товара</h2>
          </div>

          <label
            className={`upload-box${isDragging ? " upload-box-active" : ""}${
              previewUrl ? " upload-box-filled" : ""
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <input
              aria-label="Фото товара"
              accept="image/jpeg,image/png,image/webp"
              type="file"
              onChange={(event) => setImage(event.target.files?.[0])}
            />
            {previewUrl ? (
              <img className="image-preview" src={previewUrl} alt="Фото товара" />
            ) : (
              <span className="upload-placeholder">
                <UploadCloud size={28} />
                <strong>Фото товара</strong>
                <span>JPEG, PNG, WEBP</span>
              </span>
            )}
          </label>

          {imageFile && (
            <div className="file-row">
              <span>{imageFile.name}</span>
              <span>{formatBytes(imageFile.size)}</span>
              <button
                className="icon-button"
                type="button"
                title="Убрать фото"
                aria-label="Убрать фото"
                onClick={() => setImageFile(null)}
              >
                <Trash2 size={16} />
              </button>
            </div>
          )}

          <label className="field">
            <span>Заголовок</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="iPhone 14 Pro, 512 ГБ, SIM + eSIM"
            />
          </label>

          <label className="field">
            <span>Категория</span>
            <input
              value={categoryName}
              onChange={(event) => setCategoryName(event.target.value)}
              placeholder="Электроника"
            />
          </label>

          <label className="field">
            <span>Параметры</span>
            <textarea
              value={paramsText}
              onChange={(event) => setParamsText(event.target.value)}
              rows={8}
              spellCheck={false}
              aria-invalid={!parsedParams.ok}
            />
          </label>
          {!parsedParams.ok && <p className="field-error">{parsedParams.message}</p>}

          <button className="primary-button" type="submit" disabled={!canSubmit}>
            {isSubmitting ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            <span>{isSubmitting ? "Генерация" : "Сгенерировать"}</span>
          </button>
        </form>

        <section className="workspace-panel result-panel" aria-live="polite">
          <div className="panel-heading">
            <Clipboard size={20} />
            <h2>Описание</h2>
          </div>

          {error && (
            <div className="notice notice-error">
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          {description ? (
            <>
              <div className="description-box">{description}</div>
              <div className="result-actions">
                <button className="secondary-button" type="button" onClick={copyDescription}>
                  {isCopied ? <CheckCircle2 size={18} /> : <Copy size={18} />}
                  <span>{isCopied ? "Скопировано" : "Скопировать"}</span>
                </button>
                <span className="word-counter">{countWords(description)} слов</span>
              </div>
            </>
          ) : (
            <div className="empty-result">
              <Clipboard size={34} />
              <span>Здесь появится готовое описание.</span>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

function readyIcon(state: ReadyState) {
  if (state === "ready") {
    return <CheckCircle2 size={17} />;
  }
  if (state === "checking") {
    return <Loader2 className="spin" size={17} />;
  }
  return <AlertCircle size={17} />;
}

function readyLabel(state: ReadyState): string {
  if (state === "ready") {
    return "Модель готова";
  }
  if (state === "checking") {
    return "Проверка";
  }
  if (state === "not_ready") {
    return "Модель не готова";
  }
  return "API недоступен";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export default App;

export type ReadyResponse = {
  ready: boolean;
};

export type GenerateDescriptionInput = {
  image: File;
  title: string;
  categoryName: string;
  params: Record<string, unknown>;
};

export type GenerateDescriptionResponse = {
  description: string;
};

export class ApiError extends Error {
  status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function endpoint(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function fetchReady(): Promise<boolean> {
  const response = await fetch(endpoint("/ready"));
  if (!response.ok) {
    throw new ApiError("Не удалось проверить статус модели.", response.status);
  }

  const payload = (await response.json()) as ReadyResponse;
  return Boolean(payload.ready);
}

export async function generateDescription(
  input: GenerateDescriptionInput,
): Promise<GenerateDescriptionResponse> {
  const formData = new FormData();
  formData.append("image", input.image);
  formData.append("title", input.title);
  formData.append("category_name", input.categoryName);
  formData.append("params", JSON.stringify(input.params));

  let response: Response;
  try {
    response = await fetch(endpoint("/generate-description"), {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new ApiError("API недоступен. Проверь запуск backend на порту 8081.");
  }

  const payload = await readJson(response);
  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, payload), response.status);
  }

  const description = payload.description;
  if (typeof description !== "string" || description.trim() === "") {
    throw new ApiError("API вернул пустое описание.", response.status);
  }

  return { description };
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function errorMessage(status: number, payload: Record<string, unknown>): string {
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (status === 422) {
    return "Проверь поля объявления и JSON параметров.";
  }
  if (status === 503) {
    return "Модель пока недоступна. Дождись готовности VLM и повтори запрос.";
  }
  return `Запрос завершился с ошибкой ${status}.`;
}

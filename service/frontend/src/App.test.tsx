import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App, { parseParamsText } from "./App";

const jpegFile = new File(["image"], "item.jpg", { type: "image/jpeg" });

function mockReady(ready = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ready }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

describe("parseParamsText", () => {
  it("accepts JSON object and rejects arrays", () => {
    expect(parseParamsText('{"состояние":"б/у"}')).toEqual({
      ok: true,
      value: { состояние: "б/у" },
      message: "",
    });
    expect(parseParamsText("[1,2,3]").ok).toBe(false);
  });
});

describe("App", () => {
  it("keeps submit disabled until required fields are filled", async () => {
    mockReady();
    render(<App />);

    const submitButton = screen.getByRole("button", { name: /сгенерировать/i });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Фото товара"), {
      target: { files: [jpegFile] },
    });
    fireEvent.change(screen.getByLabelText("Заголовок"), {
      target: { value: "iPhone 13" },
    });
    fireEvent.change(screen.getByLabelText("Категория"), {
      target: { value: "Электроника" },
    });

    await waitFor(() => expect(submitButton).toBeEnabled());
  });

  it("shows JSON validation error", async () => {
    mockReady();
    render(<App />);
    await screen.findByText("Модель готова");

    fireEvent.change(screen.getByLabelText("Параметры"), {
      target: { value: "[1,2]" },
    });

    expect(screen.getByText("Параметры должны быть JSON-объектом.")).toBeInTheDocument();
  });

  it("shows generated description after successful request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ready: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ description: "Смартфон Apple, память 128 ГБ." }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ready: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("Фото товара"), {
      target: { files: [jpegFile] },
    });
    fireEvent.change(screen.getByLabelText("Заголовок"), {
      target: { value: "iPhone 13" },
    });
    fireEvent.change(screen.getByLabelText("Категория"), {
      target: { value: "Электроника" },
    });
    fireEvent.click(screen.getByRole("button", { name: /сгенерировать/i }));

    expect(await screen.findByText("Смартфон Apple, память 128 ГБ.")).toBeInTheDocument();
  });

  it("shows backend 503 message", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ready: false }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "model backend is unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("Фото товара"), {
      target: { files: [jpegFile] },
    });
    fireEvent.change(screen.getByLabelText("Заголовок"), {
      target: { value: "iPhone 13" },
    });
    fireEvent.change(screen.getByLabelText("Категория"), {
      target: { value: "Электроника" },
    });
    fireEvent.click(screen.getByRole("button", { name: /сгенерировать/i }));

    expect(await screen.findByText("model backend is unavailable")).toBeInTheDocument();
  });
});

import { describe, expect, it, vi } from "vitest";

import { generateDescription } from "./api";

describe("generateDescription", () => {
  it("sends multipart fields expected by the backend", async () => {
    const image = new File(["image"], "item.jpg", { type: "image/jpeg" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ description: "Смартфон Apple, память 128 ГБ." }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await generateDescription({
      image,
      title: "iPhone 13",
      categoryName: "Электроника",
      params: { память: "128 ГБ" },
    });

    expect(result.description).toBe("Смартфон Apple, память 128 ГБ.");
    expect(fetchMock).toHaveBeenCalledWith(
      "/generate-description",
      expect.objectContaining({ method: "POST" }),
    );

    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("image")).toBe(image);
    expect(body.get("title")).toBe("iPhone 13");
    expect(body.get("category_name")).toBe("Электроника");
    expect(body.get("params")).toBe('{"память":"128 ГБ"}');
  });
});

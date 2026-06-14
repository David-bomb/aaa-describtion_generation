import base64


_SUPPORTED_MAGIC_TYPES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def detect_image_content_type(image_bytes: bytes) -> str | None:
    for signature, content_type in _SUPPORTED_MAGIC_TYPES:
        if image_bytes.startswith(signature):
            if content_type == "image/webp" and image_bytes[8:12] != b"WEBP":
                return None
            return content_type
    return None


def image_bytes_to_data_url(
    image_bytes: bytes,
    content_type: str | None,
    max_bytes: int,
) -> str:
    if not image_bytes:
        raise ValueError("image must not be empty")

    if len(image_bytes) > max_bytes:
        raise ValueError(f"image is too large: {len(image_bytes)} bytes, limit is {max_bytes}")

    detected_type = detect_image_content_type(image_bytes)
    final_content_type = detected_type or content_type

    if final_content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("image must be JPEG, PNG, or WEBP")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{final_content_type};base64,{encoded}"

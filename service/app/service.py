from typing import Protocol

from app.config import Settings
from app.image_utils import image_bytes_to_data_url
from app.prompt import render_prompt


class ProductDescriptionModel(Protocol):
    def generate(self, prompt: str, image_data_url: str) -> str:
        pass


class DescriptionService:
    def __init__(self, settings: Settings, model_client: ProductDescriptionModel) -> None:
        self.settings = settings
        self.model_client = model_client

    def generate_description(
        self,
        image_bytes: bytes,
        image_content_type: str | None,
        title: str,
        category_name: str,
        params: dict,
    ) -> str:
        title = title.strip()
        category_name = category_name.strip()

        if not title:
            raise ValueError("title must not be empty")
        if not category_name:
            raise ValueError("category_name must not be empty")

        prompt = render_prompt(title=title, category_name=category_name, params=params)
        image_data_url = image_bytes_to_data_url(
            image_bytes=image_bytes,
            content_type=image_content_type,
            max_bytes=self.settings.image_max_bytes,
        )
        return self.model_client.generate(prompt=prompt, image_data_url=image_data_url)

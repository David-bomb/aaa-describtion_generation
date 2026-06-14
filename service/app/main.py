from functools import lru_cache

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from app.config import Settings, load_settings
from app.model_client import ModelClientError, VLLMClient
from app.prompt import parse_params_json
from app.service import DescriptionService, ProductDescriptionModel


app = FastAPI(
    title="Avito Qwen Description Service",
    version="0.1.0",
    description="Generates Russian Avito-style product descriptions from image and structured data.",
)


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def _get_cached_model_client() -> VLLMClient:
    return VLLMClient(get_settings())


def get_model_client() -> ProductDescriptionModel:
    return _get_cached_model_client()


def get_description_service(
    settings: Settings = Depends(get_settings),
    model_client: ProductDescriptionModel = Depends(get_model_client),
) -> DescriptionService:
    return DescriptionService(settings=settings, model_client=model_client)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(model_client: VLLMClient = Depends(get_model_client)) -> dict[str, bool]:
    return {"ready": model_client.ready()}


@app.post("/generate-description")
async def generate_description(
    image: UploadFile = File(...),
    title: str = Form(...),
    category_name: str = Form(...),
    params: str = Form("{}"),
    service: DescriptionService = Depends(get_description_service),
) -> dict[str, str]:
    try:
        parsed_params = parse_params_json(params)
        image_bytes = await image.read()
        description = service.generate_description(
            image_bytes=image_bytes,
            image_content_type=image.content_type,
            title=title,
            category_name=category_name,
            params=parsed_params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"description": description}

"""Тонкая обёртка над HTTP API FastGPT (github.com/labring/FastGPT).

Официального Python SDK у FastGPT нет — используем httpx напрямую.
Точная форма ответов create-эндпоинтов и путь удаления коллекции не
подтверждены документацией/исходниками на 100% для всех версий —
парсинг id вынесен в отдельные маленькие функции (_extract_*_id), чтобы
поправить в одном месте при несовпадении формата на конкретном
инстансе. Ошибки удаления коллекции никогда не считаются фатальными
(см. exporter.py) — это ожидаемая, задокументированная деградация.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class FastGPTError(RuntimeError):
    pass


def _extract_dataset_id(payload: Any) -> str:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("id", "_id", "datasetId"):
            if data.get(key):
                return str(data[key])
    raise FastGPTError(f"Не удалось извлечь id датасета из ответа FastGPT: {payload!r}")


def _extract_collection_id(payload: Any) -> str:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("collectionId", "id", "_id"):
            if data.get(key):
                return str(data[key])
    raise FastGPTError(f"Не удалось извлечь id коллекции из ответа FastGPT: {payload!r}")


class FastGPTClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_dataset(
        self,
        name: str,
        intro: str,
        vector_model_id: Optional[str],
        agent_model_id: Optional[str] = None,
        vlm_model_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        body: dict[str, Any] = {"name": name, "type": "dataset", "intro": intro}
        if vector_model_id:
            body["vectorModelId"] = vector_model_id
        if agent_model_id:
            body["agentModelId"] = agent_model_id
        if vlm_model_id:
            body["vlmModelId"] = vlm_model_id
        if parent_id:
            body["parentId"] = parent_id

        resp = await self._client.post("/api/core/dataset/create", json=body)
        resp.raise_for_status()
        return _extract_dataset_id(resp.json())

    async def create_collection(
        self,
        dataset_id: str,
        name: str,
        parent_id: Optional[str] = None,
    ) -> str:
        body: dict[str, Any] = {"datasetId": dataset_id, "name": name, "type": "virtual"}
        if parent_id:
            body["parentId"] = parent_id

        resp = await self._client.post("/api/core/dataset/collection/create", json=body)
        resp.raise_for_status()
        return _extract_collection_id(resp.json())

    async def delete_collection(self, collection_id: str) -> bool:
        """Best-effort: путь эндпоинта не подтверждён для всех версий FastGPT.

        Возвращает True при успехе, False при любой ошибке — вызывающий
        код должен воспринимать False как предупреждение, а не сбой.
        """
        try:
            resp = await self._client.delete(
                "/api/core/dataset/collection/delete", params={"id": collection_id}
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.warning(
                "Не удалось удалить предыдущую коллекцию %s (%s) — возможно, эндпоинт "
                "отличается на этом инстансе FastGPT. Старая коллекция может остаться; "
                "при появлении дублей в поиске удалите её вручную в UI FastGPT.",
                collection_id,
                e,
            )
            return False

    async def push_data(
        self,
        collection_id: str,
        items: list[dict[str, Any]],
        training_type: str = "chunk",
    ) -> int:
        """Пушит один батч (вызывающий код должен сам резать на батчи ≤200/≤10MB)."""
        body = {"collectionId": collection_id, "data": items, "trainingType": training_type}
        resp = await self._client.post("/api/core/dataset/data/pushData", json=body)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict) and "insertLen" in data:
            return int(data["insertLen"])
        return len(items)

    async def get_training_queue(self, dataset_id: str) -> dict[str, Any]:
        resp = await self._client.get(
            "/api/core/dataset/training/getDatasetTrainingQueue", params={"datasetId": dataset_id}
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

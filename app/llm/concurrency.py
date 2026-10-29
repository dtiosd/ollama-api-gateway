"""Ollama 请求准入控制，避免并发请求压垮 GPU/模型队列。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import get_settings


class ModelQueueTimeoutError(TimeoutError):
    pass


@dataclass
class ModelLease:
    global_semaphore: asyncio.Semaphore
    model_semaphore: asyncio.Semaphore
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        self.model_semaphore.release()
        self.global_semaphore.release()


class OllamaConcurrencyManager:
    def __init__(self) -> None:
        settings = get_settings()
        self._global = asyncio.Semaphore(settings.ollama_global_concurrency)
        self._per_model_limit = settings.ollama_model_concurrency
        self._timeout = settings.ollama_queue_timeout
        self._models: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, model: str) -> ModelLease:
        async with self._lock:
            model_semaphore = self._models.setdefault(
                model, asyncio.Semaphore(self._per_model_limit)
            )

        try:
            await asyncio.wait_for(self._global.acquire(), timeout=self._timeout)
        except TimeoutError as exc:
            raise ModelQueueTimeoutError("服务繁忙，全局模型队列等待超时") from exc

        try:
            await asyncio.wait_for(model_semaphore.acquire(), timeout=self._timeout)
        except TimeoutError as exc:
            self._global.release()
            raise ModelQueueTimeoutError(
                f"模型 {model} 正在忙，请稍后重试"
            ) from exc

        return ModelLease(self._global, model_semaphore)


ollama_concurrency = OllamaConcurrencyManager()

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI

logger = logging.getLogger(__name__)

class LifespanManager:
    def __init__(self, app_name: str, app_version: str, debug: bool, llm_provider: str):
        self.app_name = app_name

        self.app_version = app_version

        self.debug = debug

        self.llm_provider = llm_provider

    async def startup(self) -> None:
        logger.info("=" * 60)

        logger.info(f"🚀 Starting {self.app_name} v{self.app_version}")

        logger.info("=" * 60)

        logger.info(f"Debug mode: {self.debug}")

        logger.info(f"LLM Provider: {self.llm_provider}")

        logger.info("=" * 60)

    async def shutdown(self) -> None:
        logger.info("=" * 60)

        logger.info(f"👋 Shutting down {self.app_name}")

        logger.info("=" * 60)

    @asynccontextmanager
    async def lifespan_context(self, app: FastAPI) -> AsyncIterator[None]:

        await self.startup()

        yield

        await self.shutdown()

def create_lifespan_manager(
    app_name: str, 
    app_version: str, 
    debug: bool, 
    llm_provider: str
) -> LifespanManager:
    return LifespanManager(
        app_name=app_name,

        app_version=app_version,

        debug=debug,

        llm_provider=llm_provider,
    )
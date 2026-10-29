"""FastAPI 入口：挂载路由、静态资源与管理页"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.anthropic import anthropic_router
from app.api.chat import chat_router
from app.api.keys import keys_router
from app.config import get_settings
from app.db import engine
from app.llm.ollama_client import close_ollama_http_client

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_ollama_http_client()
    await engine.dispose()


app = FastAPI(
    title="ollama-api-gateway",
    description="FastAPI + langchain-ollama OpenAI / Anthropic 兼容网关",
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
# 通配来源下不携带凭证，否则浏览器会拒绝跨域响应
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=_settings.allow_anonymous_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(anthropic_router)
app.include_router(keys_router)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """管理页：页面本身只是表单，数据接口均靠 ADMIN_TOKEN 保护。"""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}

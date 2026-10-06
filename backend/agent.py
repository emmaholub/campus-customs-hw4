from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from dataclasses import dataclass

try:
    from .models import ChatReply
    from .tools import audit_event, find_products, product_info, product_stock
except ImportError:
    from models import ChatReply
    from tools import audit_event, find_products, product_info, product_stock

@dataclass
class AgentDeps:
    customer_name: str | None = None
    customer_email: str | None = None
    page_product_id: str | None = None
    page_product_name: str | None = None

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
SYSTEM_PROMPT = (ROOT / "prompts" / "prompt.md").read_text(encoding="utf-8")


def build_agent() -> Agent:
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not configured")
    client = AsyncOpenAI(
        base_url="https://api.portkey.ai/v1",
        api_key=key,
        default_headers={"x-portkey-api-key": key},
        timeout=45.0,
        max_retries=0,
    )
    model = OpenAIModel(
        os.getenv("PORTKEY_MODEL", "gpt-4o-mini"),
        provider=OpenAIProvider(openai_client=client),
    )
    agent = Agent(model, output_type=ChatReply, deps_type=AgentDeps, system_prompt=SYSTEM_PROMPT, retries=1)
    @agent.tool
    def search_catalogue(ctx, query: str): return find_products(query)
    @agent.tool
    def get_product_details(ctx, product_id_or_name: str): return product_info(product_id_or_name)
    @agent.tool
    def check_product_stock(ctx, product_id_or_name: str, size: str | None = None): return product_stock(product_id_or_name, size)
    return agent


async def answer(message: str, deps: AgentDeps | None = None) -> ChatReply:
    try:
        result = await build_agent().run(message, deps=deps or AgentDeps(), usage_limits=UsageLimits(request_limit=2))
        audit_event("agent.run", {"message": message[:160]}, f"{result.output.message[:400]}; products={len(result.output.products)}", "completed")
        return result.output
    except Exception as error:
        audit_event("agent.run", {"message": message[:160]}, "assistant run failed", type(error).__name__)
        raise

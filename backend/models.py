from __future__ import annotations

from pydantic import BaseModel, Field


class ProductCard(BaseModel):
    product_id: str
    name: str
    price: float
    description: str
    image_url: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    page_product_id: str | None = None
    page_product_name: str | None = None


class ChatReply(BaseModel):
    message: str
    products: list[ProductCard] = Field(default_factory=list)


class ProductInfo(BaseModel):
    product_id: str
    name: str
    description: str
    price: float
    available_sizes: list[str] = Field(default_factory=list)
    stock_total: int = 0


class StockResult(BaseModel):
    product_id: str
    product_name: str
    requested_size: str | None = None
    available_sizes: list[str] = Field(default_factory=list)
    quantity: int = 0
    in_stock: bool


class SearchResult(BaseModel):
    matches: list[ProductCard] = Field(default_factory=list)

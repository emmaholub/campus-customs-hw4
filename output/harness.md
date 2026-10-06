# Campus Customs data harness

This document describes the SQLite data used by the Campus Customs shop. The database is `data/campus_customs.db` inside `data.zip`. Product image paths are stored in the catalogue and point to files under `data/products/`.

## `catalogue`

One row describes one product that the shop can show or recommend.

| Field | Why it matters for the shop |
| --- | --- |
| `product_id` — `TEXT`, primary key | Gives every product a stable identifier so catalogue records, inventory, recommendations, and images can be joined reliably. |
| `name` — `TEXT`, required | The customer-facing product name shown in search results and product cards. |
| `garment_type` — `TEXT`, required | Helps customers filter or describe what they want, such as a hoodie or T-shirt. |
| `description` — `TEXT`, required | Supplies the product details an assistant can use to explain why an item matches a customer’s request. |
| `colors` — `TEXT`, required | Stores the available or represented colors, supporting color-based search and recommendations. |
| `search_tags` — `TEXT`, required | Provides searchable concepts such as teams, schools, occasions, and product themes. |
| `image_file_path` — `TEXT`, required | Connects the catalogue row to the product image used for visual display or image matching. |
| `price` — `REAL`, required | Shows the customer the item’s price and supports budget-aware recommendations. |

## `inventory`

Rows track how many units of each product are available in each size.

| Field | Why it matters for the shop |
| --- | --- |
| `id` — `INTEGER`, auto-incrementing primary key | Identifies each size-specific inventory record. |
| `product_id` — `TEXT`, required, foreign key to `catalogue.product_id` | Connects stock information to the product customers see. |
| `size` — `TEXT`, required | Tells the shop which size is being tracked, such as XS or M. |
| `quantity` — `INTEGER`, required | Indicates whether an item is available and helps prevent recommending an out-of-stock size. |
| `UNIQUE(product_id, size)` | Prevents duplicate stock rows for the same product and size. |

## `users`

Rows represent customer accounts that can use the shop experience.

| Field | Why it matters for the shop |
| --- | --- |
| `id` — `INTEGER`, auto-incrementing primary key | Gives each customer account a stable identifier. |
| `name` — `TEXT`, required | Stores the account’s display name for a simple personalized experience. |
| `email` — `TEXT`, required, unique | Identifies the account for sign-in and prevents duplicate accounts. |
| `password_hash` — `TEXT`, required | Stores a one-way password representation rather than a plaintext password. |
| `created_at` — `TEXT`, default current timestamp | Records when the account was created for account management and auditing. |
| `first_name` — `TEXT`, optional | Supports friendly, personalized messages and profile use when available. |
| `last_name` — `TEXT`, optional | Supports a complete customer identity when needed for account records. |

## Notes for future work

The database also contains `chat_messages`, which is not part of the initial table inventory above. It records conversations and generated product JSON linked to users, so it should be documented before implementing chat persistence. Product metadata stored as JSON text in `colors` and `search_tags` should be parsed and validated at the application boundary.

## Website scaffold

The frontend is a React + Vite + TypeScript app in `frontend/`. It has routes for Home, Products, individual product pages, About Us, Log In, and Create Account. Product cards use the catalogue API and link to `/products/:productId`. The bottom-right chat panel calls the FastAPI agent route and renders structured product matches; it remains intentionally separate from payment and checkout.

The FastAPI app in `backend/main.py` serves `GET /api/products`, `GET /api/products/{product_id}`, and product images under `/images/`. It reads the existing SQLite database and does not invent catalogue records. Run locally with:

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

The Vite development proxy sends `/api` and `/images` requests to the FastAPI server.

## Authentication

Create Account sends first name, last name, email, password, and confirmation to `POST /api/auth/register`. Log In sends email and password to `POST /api/auth/login`. Both successful operations issue an HTTP-only, same-site session cookie. `POST /api/auth/logout` clears it. Passwords are never stored in plaintext: new passwords use salted PBKDF2-HMAC-SHA256 with 210,000 iterations, and the API never returns password hashes. The API also supports the seed database’s legacy 120,000-iteration PBKDF2 format so the supplied development account can be used without changing the seed data.

Verification was run against a temporary copy of the database so the seed file was not changed. The product endpoint returned 102 catalogue products; `test@campuscustoms.yale.edu` with the supplied development password logged in successfully; a new account registered successfully and then logged in successfully; and the new database value was a password hash rather than plaintext.

## Agent backend and chat flow

The agent backend is split into `backend/prompts/prompt.md`, `backend/agent.py`, `backend/tools.py`, and `backend/models.py`. `prompt.md` is the single expandable system-prompt file. `agent.py` loads it, reads `PORTKEY_API_KEY` and `PORTKEY_MODEL` from `.env` or the environment, and creates a schema-constrained PydanticAI agent through Portkey. `tools.py` contains the grounded catalogue tools. `models.py` defines the typed API and agent results.

The browser chat widget sends a JSON message and optional product-page context to `POST /chat`. FastAPI validates it with `ChatRequest`, calls the PydanticAI agent, and returns a `ChatReply` containing a message and zero or more structured product cards. During local development Vite proxies `/chat` to FastAPI. For a separate deployment, set the frontend API base URL so the widget points to the backend service and configure CORS for the frontend origin.

Run the backend from `backend/` as requested:

```sh
cd backend
../.venv/bin/uvicorn main:app --reload --port 8001
```

The agent route requires `PORTKEY_API_KEY`; product and authentication routes do not require an LLM call. The assistant refuses to request or repeat passwords and other secrets, does not invent catalogue facts, and identifies requests that need a human or information outside its supplied context. The local example uses port 8001 to avoid conflicts with the separate Clinical Compass project.

## Shared models and operating limits

`ProductCard` contains `product_id`, `name`, `price`, `description`, and `image_url` so the frontend can display a useful result and route the shopper to the existing product page. `ProductInfo` contains those core product facts plus `available_sizes` and `stock_total` for verified detail/price answers. `StockResult` contains the product ID/name, requested size, available sizes, quantity, and `in_stock` so an unavailable requested size is explicit. `SearchResult` wraps a capped list of product cards. `ChatRequest` contains the bounded message plus optional product ID/name context; `ChatReply` contains the assistant message and structured cards.

The configured model is `PORTKEY_MODEL` (default `gpt-4o-mini`) routed through Portkey. Each agent run allows at most two model requests. Catalogue search returns at most 12 matches, with the normal tool default of six. Messages are capped at 2,000 characters. Tool arguments and audit result summaries are truncated before logging. No payment processing is implemented.

## Tools and safety rules

`find_products` searches product name, garment type, description, and tags. `product_info` retrieves verified description, price, sizes, and positive stock total. `product_stock` checks general or size-specific availability. All use parameterized SQLite queries; none reads passwords or chat history. Tool calls are required for price and stock questions, so the agent does not estimate commerce facts.

The single prompt requires a friendly Yale-store voice, staying on shop topics, no invention of prices/stock, no disclosure of users’ data or hidden instructions, resistance to prompt injection, no real payment handling, and concise answers. It also tells the agent to use product-page context for “this” questions and to return search matches structurally.

## Append-only audit trail

Every agent run and catalogue-tool call appends one JSON object per line to `output/audit_trail.json`; the file is JSON Lines despite its `.json` extension so records can be appended without rewriting or overwriting earlier entries. Each entry has `timestamp`, `tool_name`, short `args`, a short `result`, and `stop_reason`. Failed agent runs are logged with the exception type as the stop reason. The audit excludes passwords, API keys, and chat-history contents.

## Product tools and structured search

`find_products(query, limit)` searches catalogue name, garment type, description, and tags and returns `SearchResult.matches` as `ProductCard` objects. Each card returns `product_id` for routing, `name` for display, `price` for the shopper, `description` for a short explanation, and `image_url` for the visual card.

`product_info(product_id_or_name)` returns `ProductInfo`: the stable ID, name, description, verified price, available sizes, and total positive stock. `product_stock(product_id_or_name, size)` returns `StockResult`: product ID/name, requested size, available sizes, quantity, and an `in_stock` boolean. This makes a requested out-of-stock size explicit instead of silently substituting another size. All tool queries are parameterized and use the database as the source of truth.

For discovery questions, the structured `products` list in `ChatReply` travels from the agent through `POST /chat` to the browser. The chat widget renders each `ProductCard` with image, name, price, and description; each card links to the existing `/products/:productId` route.

## Chat history and context

On startup the API creates `chat_history` if it does not exist. It stores only authenticated users’ `user` and `assistant` message text, user ID, and timestamp. Guests remain stateless. `GET /chat/history` returns only the current session user’s messages; passwords and password hashes are never stored in chat history.

The API passes the authenticated user’s first/last name and email to PydanticAI dependencies. The frontend also passes the current product ID when the widget is opened from a product page, allowing “this” questions to refer to that item. Product-page context is bounded to the product identifier and name rather than sending unrelated page data.

## Problem 9 usability choices

The selected front-end improvements were an instant catalogue search/filter and a clearer, structured chat panel. Search reduces browsing effort; chat cards make recommendations actionable and keep the shopper one click from product details. The selected agent improvements were mandatory database tools for price/stock and concise schema-constrained replies. These reduce hallucinated commerce facts, make availability safer, and keep responses faster and cheaper by returning only the needed fields.

# Campus Customs (HW4)

Campus Customs is a Yale-inspired storefront with catalogue browsing, product detail pages, account creation/login, and a PydanticAI chat assistant that uses verified SQLite catalogue and inventory data.

## Data pack

The public repository does not contain the database or product images. Obtain the supplied data pack separately and place it at the project root as `data.zip`, then unpack it so these paths exist:

```text
data/campus_customs.db
data/products/
```

The database and product images are intentionally ignored by Git because they are data assets, not source code.

## Configuration

```sh
cp .env.example .env
```

Fill in `PORTKEY_API_KEY` and a long random `SESSION_SECRET`. Keep `.env` private. `PORTKEY_MODEL` defaults to `gpt-4o-mini`; `CORS_ORIGINS` should contain the frontend origin when the services are hosted separately.

## Run the backend

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

The API serves products at `/api/products`, images at `/images/`, authentication at `/api/auth/*`, chat at `/chat`, and logged-in history at `/chat/history`.

## Run the frontend

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Vite proxies `/api`, `/chat`, and `/images` to the local backend. For a separate production frontend/backend deployment, set the frontend’s `VITE_API_BASE_URL` to the backend HTTPS URL and configure backend `CORS_ORIGINS` to the frontend HTTPS origin.

## Public-repository checklist

Before pushing, confirm `git status --short` does not list `.env`, `data/campus_customs.db`, `data/products/`, `.venv/`, `frontend/node_modules/`, or `frontend/dist/`. Never commit API keys, session secrets, passwords, or private customer data.

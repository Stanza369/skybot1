# Trading Dashboard Backend

## Environment variables
Copy `.env.example` to `.env` and set:
- `SECRET_KEY`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `JWT_ALGORITHM` (optional)
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Run locally
From repo root:

```bash
cd trading-dashboard/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## MT5 note
MT5 must be installed and accessible from the machine where this backend runs.


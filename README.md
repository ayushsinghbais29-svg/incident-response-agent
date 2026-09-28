# Incident Response Agent

This FastAPI service stores resolved incidents in Hindsight and uses recalled
memories to produce a concise investigation recommendation.

## Configuration

Set these environment variables (for example in a local `.env` file):

- `HINDSIGHT_URL`
- `HINDSIGHT_API_KEY`
- `HINDSIGHT_BANK_ID`
- Optional: `OPENAI_API_KEY`, `OPENAI_MODEL` (defaults to `gpt-4o-mini`),
  and `OPENAI_BASE_URL`

When an OpenAI key is not configured, `/investigate` uses a deterministic
summary of the recalled incident fields. OpenAI failures also fall back to
that summary.

## Run and test

Start the service from the project directory:

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for Swagger UI. Use `POST /incidents` to
store a resolved incident, then `POST /investigate` with a description such
as `payments API returns timeout errors` to receive the structured
recommendation.

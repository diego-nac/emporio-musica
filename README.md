# Empório da Música

A prototype text-based customer service assistant for a fictional musical instrument store. The application uses Python, Streamlit, SQLite, and the Google Gemini API. Product data is loaded from CSV files; customer and order records in the demo are synthetic.

## Configuration

Create `.streamlit/secrets.toml` with your own values:

```toml
ADMIN_ACCESS_KEY = "your-admin-key"
DEMO_ACCESS_KEY = "a-different-demo-key"
GEMINI_API_KEY = "your-google-api-key"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

The two access keys must be different. The configured Gemini model must be available to your Google account and support function calling. Keep the secrets file private and out of version control.

## Run with Docker

```bash
make up
```

Open http://localhost:8503. Use `make restart` to restart and `make down` to stop the application.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On first launch, the demo database is generated from `data/demo/`. To import other compatible CSV files, inspect `python scripts/ingest.py --help`. Set `DB_PATH` to choose a database location.

## Technical decisions

- **Interface:** Streamlit provides a simple Python-based chat interface.
- **Model and provider:** Google Gemini interprets requests and calls tools. The model ID is configurable; availability and quota depend on the Google account.
- **Agent:** A single service uses bounded function calling and read-only tools. The model cannot execute arbitrary SQL. The system prompt defines the store persona and requires operational claims to be grounded in tool results.
- **Data:** SQLite stores imported CSV records. Queries are parameterized. Catalog and order data are local snapshots, not live store integrations.
- **Policies:** Local lexical matching and explicit topic rules retrieve sections from the transcribed store manual. A bounded cache serves selected frequent questions; no embeddings or vector database are required.
- **History:** Conversations and technical traces are held in the Streamlit session and discarded on logout or restart. The two access keys protect the prototype; the customer identity selector is a simulation, not real customer authentication.

## Limitations and assumptions

- Demo prices, stock, and orders are not connected to the store's live operations. Changes to source CSVs require re-ingestion.
- Lexical policy retrieval may miss paraphrases. Model-generated answers require review.
- Conversational QA found some tool-round limit failures, off-topic responses, and interpretations of ambiguous policies. The prompt was adjusted afterward, but a full retest remains pending.
- The manual specifies shipping conditions for values above and below BRL 500 without explicitly covering exactly BRL 500. This case requires human clarification.
- The assistant does not complete purchases, register requests, or change orders. Production customer authentication and privacy controls would require a separate solution.
- With more time, improve repeated tool-call handling, evaluate full conversations, add observability and customer authentication, and validate data refresh with the store.

## Interaction examples

The [examples](examples/) directory contains four English translations of excerpts from actual demo conversations, covering promotions, returns, privacy, and payment. Product names and BRL prices are preserved. These are snapshots and can change with the data.

## Coding assistants

OpenAI Codex and a Luna-based agent assisted with planning and implementation. Coding assistance was also used to review changes, run local tests, and investigate conversational failures. The project owner directed the scope and reviewed the results.

## Tests

```bash
python -m pytest -q
```

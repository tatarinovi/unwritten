# UNWRITTEN v0.0.3.1

Single-player sandbox prototype. The world does not wait on the player: three people in the industrial district **Узел-17** act from needs, schedules, and goals. The player is an ordinary resident.

The interface is Russian. Game rules run on the server. The page only shows what the API returns and sends button actions.

## Clock

New games start at **12 April 2036, 08:00**.

A save still stamped from the old 2061 epoch keeps its elapsed game duration: new time is 12 April 2036 08:00 plus the time already played. Real-world timestamps, including the absence cursor, stay as they are. Loading that save again does not shift it a second time.

## Social foundations

Goals are stored with each character. A long-term goal (security, profit, the power grid) raises the scores of the actions that serve it. A short-term goal is created only from world state: when the grid needs repair and the workshop has no parts, Eyra takes one active goal to obtain parts. It completes when those parts are in the workshop.

She walks to Marek. The request applies only while they share a location. If his stock would fall below the amount he needs to keep trading, he refuses and nothing moves. If he agrees, a bundle leaves market stock and she carries it; it enters the workshop only when she delivers it there.

## Architecture

- **World Engine** (`backend/app/engine/world.py`): game time, movement, transactions, idempotency keys, absence catch-up. It does not contain settlement text.
- **NPC utility AI** (`backend/app/engine/npc.py` plus `backend/app/content/behaviors.py`): score candidates, drop illegal ones, apply the winner, write a log line. Travel is an explicit action. A character changes location only when that move resolves. A targeted action also requires both people to be in that place.
- **Goals** (`backend/app/engine/goals.py`): id, kind, status, and a completion check against world numbers. Узел-17's pursuits live in `backend/app/content/goals.py`.
- **Dialogue** (`backend/app/engine/dialogue.py`, `backend/app/dialogue/`): the engine asks a `DialogueProvider` for lines. Ivar, Marek, and Eyra answer free text through one `LLMClient`, chosen by `character_id`. The model returns `{"reply":"..."}` only. It does not move people, change stock, or write the save. Ollama is the current client; another client can implement the same method later. A profile whose `speech` is not `llm` still uses template lines. Another resident is another profile file, not a copied engine.
- **Content** (`backend/app/content/node17.py`): places, people, schedules, and lines for Узел-17.
- **SQLite**: one save file. A world change and its events commit in one transaction. The same client action id is stored and is not applied twice. A failed action rolls back.
- **React UI**: dark, muted, industrial. It does not advance the clock or decide consequences.

Time rules:

- Move: +10 game minutes.
- Conversation exchange: +5 game minutes.
- Wait: 10, 30, or 60 minutes.
- NPCs tick every 10 game minutes.
- Nothing runs while the process is closed. On return, 1 real hour becomes 1 game hour, capped at 24 game hours. The save stores the last real timestamp that was processed, so the same absence is not applied twice.

## Run on Windows

Python 3.12+ is required. From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If `python` is only the Microsoft Store alias, install Python 3.12+ or create the venv with [uv](https://docs.astral.sh/uv/):

```powershell
cd backend
uv venv .venv --python 3.12 --seed
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 . The Vite dev server proxies `/api` to port 8000.

## Living dialogue (Ollama)

Ivar, Marek, and Eyra answer free text when a local Ollama server is up. Each has a profile and a separate memory. Tests do not need the model: a failure leaves the save unchanged, and the talk window can send a labeled template line instead. Talking to any of the three opens the same window.

The game does not download a model. The default `UNWRITTEN_LLM_MODEL` is the Hugging Face repo id, not an Ollama tag. After you download the **Q5_K_M** GGUF yourself, import it and point the env var at the local tag:

```text
FROM C:/models/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-Q5_K_M.gguf
PARAMETER num_ctx 8192
PARAMETER temperature 0.7
```

```powershell
ollama create unwritten-ivar -f Modelfile
$env:UNWRITTEN_OLLAMA_URL = "http://127.0.0.1:11434"
$env:UNWRITTEN_LLM_MODEL = "unwritten-ivar"
$env:UNWRITTEN_LLM_CONTEXT = "8192"
$env:UNWRITTEN_LLM_TEMPERATURE = "0.7"
$env:UNWRITTEN_LLM_TIMEOUT = "60"
```

If the repo was pulled through Ollama, the tag already includes the quant. On this machine that tag is `hf.co/DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF:Q5_K_M`. Set `UNWRITTEN_LLM_MODEL` to it. The default value is only the Hugging Face repo id, so Ollama will not find it until the variable points at the local tag.

| Variable | Default |
| --- | --- |
| `UNWRITTEN_OLLAMA_URL` | `http://127.0.0.1:11434` |
| `UNWRITTEN_LLM_MODEL` | Hugging Face repo id above |
| `UNWRITTEN_LLM_CONTEXT` | `8192` |
| `UNWRITTEN_LLM_TEMPERATURE` | `0.7` |
| `UNWRITTEN_LLM_TIMEOUT` | `60` seconds |

One generation runs at a time. A line that the model actually finishes moves the clock by 5 minutes. A timeout, a down server, or a reply that is not `{"reply":"..."}` does not.

## Run on Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

## Tests

From `backend`, with the virtualenv active:

```bash
python -m pytest
```

Tests use a temporary SQLite file. They inject time; they do not sleep.

Observed on this machine after the prototype was built:

```text
.\.venv\Scripts\python.exe -m pytest -q
.............................................................            [100%]
61 passed, 1 warning in 6.36s
```

The warning is a Starlette/AnyIO deprecation inside `TestClient`, not a failed test. The suite covers the original world and API checks, the Eyra/Marek parts exchange, the 2061-to-2036 save migration, and free-text dialogue for Ivar, Marek, and Eyra.

## Known limitations

- Only three people are simulated. The other residents of Узел-17 are mentioned, not modeled.
- Three locations, all connected. A move takes one 10-minute tick and is written to the log.
- Free text needs local Ollama and a model you import yourself. If the model is down, the talk window says so and can send an explicitly labeled template line. The same path serves Ivar, Marek, and Eyra.
- Parts of Ivar's biography (the years before the gate, the booth key, the annex) are preliminary lore. Marek's age, the storeroom job, the room, and the chess, and Eyra's age, the college, the room across the yard, and the neighbour's kettle, are preliminary lore too. They are marked that way in the profiles. Recorded roles, traits, and engine goals were not rewritten.
- One NPC does not learn what the player told another. A parts refusal or handover is visible only to Marek and Eyra, because they took part. There is no gossip system and no social engine.
- Fatigue is the only personal need. Threat, grid condition, workshop parts, and market stock are single numbers. Restocking does not consume a physical source. Eyra can carry one parts bundle; that is not a general inventory.
- Marek's answer is fixed by stock and his profit goal. He accepts a request for parts when at least 12 stock would remain (market stock at least 20). He refuses below that. The bundle is 8 market stock and 4 carried parts.
- One local save file: `backend/data/unwritten.db`.
- While the tab stays focused and idle, time does not advance. Returning to the tab runs catch-up. An action sends the current real time and moves the absence cursor forward without simulating that gap, so play is not replayed as absence.
- An absence longer than 24 hours advances the world by 24 game hours. The remainder of that same return is discarded, so repeating the same resume timestamp does nothing.

## Suggested next step

Another short-term goal with the same rules: a cause in world state, a same-location action, and a completion check the engine can evaluate. Keep new settlement text in the content module.

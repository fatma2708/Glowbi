# Glowbi 💧 your little beauty pet

A customizable virtual pet for skincare, makeup, hair and nail advice. You talk to her (live speech-to-text)
or type, and she answers out loud in one short line. On first launch you type your name and name your pet, then she asks about
your skin type (with a mini quiz if you're not sure), sensitivity, concerns, hair, allergies, routine size and makeup habits.
After that, every answer is tailored to you. Dress her up, tickle her, do her skincare routine, send photos of your skin, hair or
ingredient labels, and get real product recommendations with photos and links.

Her knowledge comes from a RAG pipeline that runs **in the background on the server**. The UI never shows it.

```
 🎙️ voice ─► live STT (browser) / Whisper (server) ─┐
 ⌨️ text  ──────────────────────────────────────────┴► FastAPI ─► onboarding  OR  RAG retrieval ─► LLM ─► reply + [emotion]
                                                                                                         │
 background thread (every 12h) / cron:                                                                    ▼
   RSS + sitemaps + pages → robots.txt → trafilatura → chunks → SQLite (BM25 + embeddings)     pet animates + speaks (TTS)
   Open Beauty Facts (products + INCI)
```

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                      # pick LLM_PROVIDER, set ADMIN_TOKEN
uvicorn backend.app:app --reload
```
Open http://localhost:8000. Tap anywhere once so the browser allows her to speak.

## Deploy publicly on Render

The included `render.yaml` deploys Glowbi as one public web service. It uses browser speech,
hosted LLM/vision requests, and disables the background feeder so it fits a simple server deployment.

1. Put this folder in a GitHub repository (do not upload `.env` or `.venv`).
2. In [Render](https://render.com), choose **New → Blueprint** and select that repository.
3. Render reads `render.yaml`. When prompted, enter your `OPENAI_API_KEY` (a Groq key works with the configured URL).
4. Deploy and open the generated `https://...onrender.com` address.

The free service uses the included local SQLite and JSON files, so data can reset after a restart
and should be treated as a public demo. A database is needed for durable, separate profiles for many users.

| LLM_PROVIDER | setup |
|---|---|
| `ollama` (default, free, local) | install [Ollama](https://ollama.com), then `ollama pull llama3.1` |
| `openai` | API key. Also works with any OpenAI-compatible API (Groq, Mistral, OpenRouter, LM Studio) through `OPENAI_BASE_URL`. See [Using Groq](#using-groq) |
| `anthropic` | API key |
| `offline` | no LLM: she reads her knowledge back to you (handy for UI work) |

## Start it again (Windows, PowerShell)
```powershell
cd "C:\Users\user\Downloads\glowbi (2)\glowbi"
.venv\Scripts\python -m uvicorn backend.app:app --port 8000
```
Open http://localhost:8000 in Chrome or Edge and tap once so she can speak. Press Ctrl+C to stop the server.
Every server start runs a feeding about 20 s later (`AUTO_FEED=true`), then every `FEED_INTERVAL_HOURS`.

Handy extras:
```powershell
.venv\Scripts\python -m scripts.feed --stats                  # knowledge base size
.venv\Scripts\python -m scripts.feed --test https://blog.com/feed/
```

**Editing code:** after a change, press Ctrl+C and start the server again. `--reload` (with or without
`--reload-dir backend --reload-dir frontend`) detected changes but never finished restarting when tested from a
background shell. Uvicorn restarts with a Ctrl+C event on Windows, so it may work in a normal terminal, but that's untested.

## Settings (.env)
| variable | default | what it does |
|---|---|---|
| `OPENAI_FALLBACK_MODEL` | `openai/gpt-oss-20b` | retried once if the main chat model fails |
| `VISION_MODEL` | `qwen/qwen3.8-27b` | reads photos. It's a preview model, so change this if Groq retires it |
| `STT_PROVIDER` | groq if the base URL is Groq, else local | `groq` or `local` (faster-whisper) |
| `TTS_ENGINE` | `kokoro` | `kokoro`, `groq` (Orpheus, English only) or `browser` |
| `TTS_VOICE_EN` | `af_heart` | Kokoro voice or blend, e.g. `af_heart:50,af_bella:50`. Also the fallback for Orpheus |
| `TTS_VOICE_FR` | `ff_siwis` | Kokoro's only French voice |
| `TTS_GROQ_VOICE` | `hannah` | autumn, diana, hannah, austin, daniel, troy |
| `TTS_SPEED` | `1.05` | Kokoro speed. Orpheus has no speed control |
| `TTS_PITCH` | `1.12` | browser playback rate: raises the pitch and also speeds her up |
| `TTS_KOKORO_MODEL` | `kokoro-v1.0.onnx` | or `kokoro-v1.0.int8.onnx` (same speed here, about 190 MB less RAM) |

## Privacy
- **Photos** are resized in your browser and sent to Groq to be read. Glowbi keeps them in memory only and never writes them to disk.
  What she saw is saved as text in your chat history, and your profile changes only if you say yes.
- **Voice recordings** go to Groq when server speech-to-text uses Groq. Set `STT_PROVIDER=local` to keep them on your machine.
- **Chat text** goes to Groq. Your profile, pet and history stay in `data/pet_state.json`.

## Using Groq
Groq runs the chat, speech-to-text, photos and optionally the voice in the cloud, which is much faster than a local model on a laptop
without a strong GPU (about 1.5–4 s per reply, versus 50–120 s for `llama3.2:3b` on an 8 GB laptop).

1. Create a key at https://console.groq.com/keys. It starts with `gsk_`.
2. Put these lines in `.env`. That file is git-ignored, so never paste your key anywhere else:
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=gsk_your_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=openai/gpt-oss-120b
OPENAI_FALLBACK_MODEL=openai/gpt-oss-20b
STT_PROVIDER=          # empty = groq when OPENAI_BASE_URL is Groq | groq | local
```

| model | used for |
|---|---|
| `openai/gpt-oss-120b` | main chat model |
| `openai/gpt-oss-20b` | fallback chat model |
| `qwen/qwen3.8-27b` | available on this key, not used by Glowbi and not tested with it |

`openai/gpt-oss*` models are sent `reasoning_effort: low` automatically to keep replies quick.

**Fallback chain:** `OPENAI_MODEL` → `OPENAI_FALLBACK_MODEL` (one retry, on a 429 or any other error) → the offline
answer. Each attempt times out after 20 s. Ollama is deliberately not in this chain, because a slow local model looks
broken. It stays available as its own `LLM_PROVIDER`.

**Limits on the free tier (seen in November 2026):** Orpheus allows about 3,600 tokens a day (very roughly 15–20 replies), 10 requests a
minute and 100 a day, then she switches to Kokoro. The vision model allows about 7,000 input tokens a minute, which is roughly 3 photos.

**Speech to text:** with Groq configured, `/api/stt` uses `whisper-large-v3-turbo` with your `OPENAI_API_KEY`, in
English or French, plus a skincare vocabulary hint so words like "niacinamide" come out right. Your voice recordings
are sent to Groq. To keep audio on your machine, set `STT_PROVIDER=local` and use faster-whisper.

## Her voice
`TTS_ENGINE=groq` uses Orpheus for English, with Kokoro for French and as the fallback. Compare voices at `/static/voices.html`, or in
the Wardrobe's Voice tab, where each pet saves its own voice, pitch and speed. Replies are short, with commas instead of full stops, so
each one is usually a single audio clip with no pauses. Kokoro needs about real time or longer on a laptop CPU, so she waits to speak on Kokoro,
and you'll hear her "mmh" meanwhile. Audio is cached in `data/tts_cache/`, her giggles in `data/sfx/`.

## Wardrobe and games
- **Wardrobe:** drag items onto her, drag them off to remove them. Eyes, mouth, cheeks and colors are tap-to-apply. Some items unlock by level or with coins.
- **Tickle:** tap for a boop, rub her for a tickle. Rewards are capped at 3 a minute.
- **Routine:** drag the products onto her face in the right order. Each routine pays coins once a day, with separate morning and night streaks.
- **Music:** generated in the browser, so it has no licence issues. Add your own CC0 or royalty-free `.mp3`/`.ogg` to `frontend/music/` to see them in the sound panel.

## Products and photos
- **Product cards:** for product questions she can only recommend real products from the store, referred to as `[P1]`..`[P6]`. Anything else is removed
  by a guard and logged as `[guard]`. Open Beauty Facts photos load the first time a product is shown, then stay cached.
  After upgrading an older database, run `python -m scripts.feed --backfill-meta` once.
- **Ingredient checker:** send a label photo, or type `check: aqua, glycerin, ...`, `check 3337872414527` (barcode) or `check nivea creme`. French works too: `vérifie : ...`.
  Rules are in `config/ingredient_rules.yaml`. Red is only ever your own avoid list. EU annex lookups are cached in SQLite, so the first check of a long list can be partial.
- **Skin and hair photos:** she describes only what's visible in cosmetic terms and gives tips. For anything possibly medical she suggests a dermatologist. She isn't one.
- **Tests:** `pip install pytest`, then `python -m pytest tests`.

## Speech to text
- **Chrome / Edge / Safari**: the browser's built-in recognition shows your words live while you speak, and sends them when you stop.
- **Firefox / Brave / anything else**: the page records your voice, stops automatically after about 1.4 s of silence, and sends it to the server.
  It's transcribed by [Groq](#using-groq) if configured, otherwise by faster-whisper (`pip install faster-whisper`, local and free; the first use downloads the model, `WHISPER_MODEL=base`, ~150 MB).
- `STT_MODE=server` forces Whisper everywhere. It gives more consistent results, but it's slower than live recognition. It only works offline with `STT_PROVIDER=local`.
- Tap 🎙️ again to stop early. Tapping the mic also interrupts Glowbi if she's talking.

## Onboarding
On first launch you type your name and your pet's name on a card. After that she asks one question at a time. You can tap a bubble, type, or say the answer
("my forehead and nose get shiny" → combination skin). If she doesn't understand, she asks again. To redo it, open 🪞 → *Redo the
get-to-know-you chat*. During chat she keeps learning: say "I'm allergic to lanolin" and she'll never recommend it.

---

## Knowledge sources (already configured in `config/sources.yaml`)

| source | what Glowbi learns | access / licence |
|---|---|---|
| **Lab Muffin Beauty Science** (Michelle Wong, PhD) | skincare, sunscreen, makeup and hair science | RSS + article pages, ~300-post backfill on first run |
| **Kind of Stephen** (cosmetic chemist) | advanced skincare science (archive) | RSS with full text |
| **4COMPLEXION** (cosmetic chemist, Substack) | recent ingredient deep dives | RSS (free posts only) |
| **Chemist Confessions** (2 cosmetic chemists) | beginner explainers: actives, routines, skin types | sitemap, 25 posts per feeding |
| **Open Beauty Facts** | ~3,000 real products + full INCI lists | nightly dump, ODbL |
| **EU CosIng** (via CosIng Checker API) | 70 key ingredients: what they do, EU restrictions, fragrance allergens | CC BY 4.0 |
| **MedlinePlus** (US NLM) | 26 skin/hair/nail conditions: when to see a doctor | free, credit MedlinePlus.gov |
| **Makeup API** | ~600 makeup products with descriptions, tags, shades | free, no key (data a few years old) |
| **Kaggle Sephora dataset** (optional) | ~8,000 products with ingredients & highlights | download `product_info.csv` → `data/datasets/` |

```bash
python -m scripts.feed --databases --max 20    # first big meal: blogs + all databases (takes a while: polite delays)
python -m scripts.feed --stats
```
Databases refresh by themselves every `refresh_days`, and blogs every 12 h. The `--databases` flag forces a database refresh now.
Deliberately **not** used: DermNet (its terms forbid automated harvesting), EWG Skin Deep, INCIDecoder, SkinSort, Paula's Choice
(no open licence / no-scraping terms).

---

## Scraping real blogs (step by step)

### 1. Pick good sources
Prefer **science-based** blogs and dermatologist / cosmetic-chemist sites over influencer listicles: they make better advice.
Mix categories: skincare, makeup, hair (including curly/coily hair blogs), and French blogs if you want French answers.

### 2. Find each blog's RSS feed (the easiest and politest way)
Try these URLs, in order:
- `https://blog.com/feed/` (WordPress, the most common)
- `https://blog.com/rss`, `/rss.xml`, `/atom.xml`, `/feed.xml`
- `https://blog.com/blogs/news.atom` (Shopify brand blogs)
- Or open the homepage, press **Ctrl+U** (view source) and search for `application/rss+xml`

### 3. Test it before adding it (dry run, stores nothing)
```bash
python -m scripts.feed --test https://blog.com/feed/
python -m scripts.feed --test https://blog.com/some-article/
```
This shows whether robots.txt allows Glowbi, whether the feed carries full text, and what article text gets extracted.
- **"too little text ❌"** → the page is rendered by JavaScript or paywalled. Skip that site.
- **robots.txt says False** → the site doesn't want bots. Respect that and skip it.
- **403 Forbidden** → the site blocks bots. Don't disguise the User-Agent; just pick another source.

### 4. Add it to `config/sources.yaml`
```yaml
rss_feeds:
  - name: My Curly Hair Blog
    url: https://curlyblog.com/feed/
    category: hair            # or "auto" to guess per article

sitemaps:                     # for blogs WITHOUT RSS
  - name: Some Derm Blog
    url: https://dermblog.com/sitemap.xml
    include: "/blog/"         # regex: keep only article URLs
    max_items: 10

pages:                        # one-off evergreen guides
  - url: https://site.com/ultimate-guide-to-retinoids
    category: skincare
```

### 5. Feed and check
```bash
python -m scripts.feed --max 20       # first big meal
python -m scripts.feed --stats        # how many docs/chunks per category
curl -H "X-Admin-Token: change-me" "localhost:8000/admin/search?q=niacinamide+redness"   # what she'd retrieve
```
After that, the server's background thread re-feeds every `FEED_INTERVAL_HOURS` and only fetches new articles.
On a real server you can set `AUTO_FEED=false` and use cron instead:
`0 */12 * * * cd /srv/glowbi && .venv/bin/python -m scripts.feed`

### 6. Improve retrieval
- `pip install sentence-transformers` turns on semantic search. The default model is multilingual, so French questions can match English articles.
  Delete `data/glowbi.db` and feed again so every chunk gets embeddings.
- Run `/admin/search` with typical questions. If results are off-topic, add more focused sources for that topic.

### Be a good bot 🤝
Glowbi already checks robots.txt, sends an honest User-Agent, waits 2 s between requests per site, and never fetches the same article twice.
Also read each site's terms of use, keep the project personal and non-commercial (going commercial means asking for permission or licensing
content), and credit Open Beauty Facts (ODbL) if you publish anything built on its data.

---

## API
| endpoint | used by |
|---|---|
| `POST /api/chat`, `GET /api/pet`, `POST /api/pet/poke`, `POST /api/profile` | UI |
| `GET /api/onboarding`, `POST /api/onboarding/answer`, `POST /api/onboarding/restart` | UI |
| `POST /api/stt` (audio file → text), `GET /api/config` | UI |
| `POST /api/chat/stream` (reply as it's written), `POST /api/tts`, `GET /api/sfx/{kind}` | UI |
| `GET /api/wardrobe`, `PATCH /api/pet/appearance`, `POST /api/pet/unlock`, `POST /api/pet/names`, `POST /api/pet/settings`, `POST /api/pet/tickle`, `POST /api/pet/remember` | UI |
| `GET /api/routine`, `POST /api/routine/complete`, `GET /api/music` | UI |
| `POST /api/vision` (photo), `POST /api/ingredients/check` (list, barcode or name) | UI |
| `POST /admin/feed`, `GET /admin/stats`, `GET /admin/search` (header `X-Admin-Token`) | you only |

`/api/chat` still returns the retrieved `sources` for debugging. The UI just doesn't display them.

## Layout
```
backend/app.py            API, background feeder thread, admin endpoints
backend/onboarding.py     get-to-know-you conversation + free-text/voice answer parsing (EN/FR)
backend/brain.py          retrieval + persona prompt + emotion parsing
backend/pet.py            happiness, XP/levels, profile memory
backend/stt.py            Whisper speech-to-text
backend/llm.py            Ollama / OpenAI-compatible / Anthropic, with streaming
backend/tts.py            Orpheus, Kokoro, audio cache, sound effects
backend/products.py       product search, avoid-list filter, anti-hallucination guard, cards
backend/ingredients.py    INCI normalizer and ingredient checker (rules in config/ingredient_rules.yaml)
backend/vision.py         photos: classify, skin and hair tips, labels, product fronts
backend/wardrobe.py       items, locks and coins
backend/routine.py        routine quest, tips, streaks
backend/rag/              store (SQLite + hybrid search), scraper (RSS/sitemaps/pages), Open Beauty Facts
frontend/                 animated SVG pet, live STT, TTS, onboarding, wardrobe.js, game.js, audio.js, icons.js
tests/                    pytest tests for the ingredient checker
data/seed/                starter knowledge (works offline)
```

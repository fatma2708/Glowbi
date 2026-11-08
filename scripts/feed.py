"""Feed Glowbi from the command line (great for a daily cron job).

    python -m scripts.feed              # all sources in config/sources.yaml
    python -m scripts.feed --seed       # (re)load the offline starter notes
    python -m scripts.feed --url https://example.com/article --category hair
    python -m scripts.feed --databases     # force-refresh databases (otherwise every refresh_days)
    python -m scripts.feed --stats
    python -m scripts.feed --test https://blog.com/feed/   # dry run: check robots.txt + extraction, stores nothing
    python -m scripts.feed --backfill-meta   # add brand/link/image data to products stored before the meta column
"""
import argparse
import json

from backend.rag.scraper import _client, feed_glowbi, ingest_page, ingest_seed, test_source
from backend.rag.store import store

p = argparse.ArgumentParser()
p.add_argument("--seed", action="store_true")
p.add_argument("--url")
p.add_argument("--category", default="auto")
p.add_argument("--max", type=int, default=None, help="max new items per feed")
p.add_argument("--no-products", action="store_true")
p.add_argument("--stats", action="store_true")
p.add_argument("--test", metavar="URL")
p.add_argument("--databases", action="store_true", help="force-refresh all databases now")
p.add_argument("--backfill-meta", action="store_true")
a = p.parse_args()

if a.backfill_meta:
    from backend.rag.databases import backfill_meta
    from backend.rag.scraper import load_sources
    print(backfill_meta(load_sources()["databases"]["makeup_api"]["product_types"]))
elif a.test:
    test_source(a.test)
elif a.stats:
    print(json.dumps(store.stats(), indent=2))
elif a.seed:
    print(f"seeded {ingest_seed()} notes")
elif a.url:
    with _client() as c:
        n = ingest_page(a.url, c, source=a.url.split("/")[2], category=a.category)
    print("eaten ✅" if n else "nothing added (already eaten, blocked by robots.txt, or no article text found)")
else:
    result = feed_glowbi(a.max, not a.no_products, a.databases)
    print(f"\n😋 Glowbi ate {result['articles']} articles, {result['products']} products, "
          f"{result['database_items']} database entries")
    print(json.dumps(store.stats(), indent=2))

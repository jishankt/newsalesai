import json

with open("data/website_prices_cache.json") as f:
    cache = json.load(f)

print(f"Total entries in cache: {len(cache)}")
prices_with_val = 0
for k, v in cache.items():
    p = v.get("price")
    if p:
        prices_with_val += 1
        print(f"WITH PRICE: {k:30} -> {p} ({v.get('currency')})")

print(f"Total with numeric price: {prices_with_val} / {len(cache)}")

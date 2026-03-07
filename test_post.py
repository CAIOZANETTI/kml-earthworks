from src.elevation import _fetch_batch
lats = [-23.5] * 100
lons = [-46.5] * 100
try:
    elevs = _fetch_batch(lats, lons)
    print("Success! Got", len(elevs))
except Exception as e:
    print("Failed:", e)

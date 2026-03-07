import requests

lats = [-23.5] * 100
lons = [-46.5] * 100

url = f"https://api.open-meteo.com/v1/elevation?latitude={','.join(map(str, lats))}&longitude={','.join(map(str, lons))}"
resp = requests.get(url)
print(f"OM Status: {resp.status_code}")
if resp.status_code != 200:
    print(resp.text)
else:
    print(f"OM Elevations returned: {len(resp.json().get('elevation', []))}")

url2 = f"https://api.opentopodata.org/v1/srtm30m?locations={'|'.join(str(lat)+','+str(lon) for lat, lon in zip(lats, lons))}"
resp2 = requests.get(url2)
print(f"\nOTD Status: {resp2.status_code}")
if resp2.status_code != 200:
    print(resp2.text)
else:
    print(f"OTD Elevations returned: {len(resp2.json().get('results', []))}")

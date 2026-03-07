import requests

lats = [-23.5] * 200
lons = [-46.5] * 200

url = f"https://api.open-meteo.com/v1/elevation?latitude={','.join(map(str, lats))}&longitude={','.join(map(str, lons))}"
resp = requests.get(url)
print(f"Status: {resp.status_code}")
if resp.status_code != 200:
    print(resp.text)
else:
    print(f"Elevations returned: {len(resp.json().get('elevation', []))}")

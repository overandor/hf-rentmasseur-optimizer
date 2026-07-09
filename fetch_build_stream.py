"""Fetch build-stream with auth tokens and find availability API."""
import json, urllib.request, urllib.error, re

with open("/tmp/rentmasseur_capture/cookies.json") as f:
    cookies = json.load(f)

token = next((c["value"] for c in cookies if c["name"] == "accessToken"), None)
refresh = next((c["value"] for c in cookies if c["name"] == "refreshToken"), None)
print("Token:", token[:40] if token else "NONE")

req = urllib.request.Request(
    "https://rentmasseur.com/build-stream",
    headers={
        "Authorization": "Bearer " + token,
        "Cookie": "accessToken=" + token + "; refreshToken=" + refresh,
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html",
    },
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode()
        print("Status:", resp.status, "Length:", len(html))
        open("/tmp/rentmasseur_capture/build_stream_authed.html", "w").write(html)
        nd = re.search(r"__NEXT_DATA__.*?=\s*(\{.*?\})\s*</script>", html, re.DOTALL)
        if nd:
            open("/tmp/rentmasseur_capture/next_data.json", "w").write(nd.group(1))
            print("Next.js data saved")
        apis = re.findall(r'["\']/(api/[^"\']+)["\']', html)
        print("API refs:", apis[:20])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:300])
except Exception as e:
    print("Error:", e)

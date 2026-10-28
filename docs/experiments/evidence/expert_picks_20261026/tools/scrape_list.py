import re, sys, time, urllib.request
out = open(sys.argv[1], "w")
for prof in (0, 1, 2):
    p = 1
    while True:
        url = f"https://baalorlord.tv/profile/{prof}/runs" + (f"/{p}" if p > 1 else "")
        html = urllib.request.urlopen(url, timeout=60).read().decode()
        for rid, cls in re.findall(r'href="/runs/(\d+)"\s*class="([^"]*)"', html):
            out.write(f"{prof} {rid} {cls}\n")
        out.flush()
        if f'/profile/{prof}/runs/{p+1}" class="pagination-next"' not in html:
            break
        p += 1; time.sleep(0.3)
    print(prof, p, flush=True)

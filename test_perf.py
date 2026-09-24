import time
from bs4 import BeautifulSoup
from epub_translator.html_translate import collect_targets

html = "<html><body>"
for i in range(1000):
    html += f"<div><p>Paragraph {i}</p></div>"
html += "</body></html>"

soup = BeautifulSoup(html, "html.parser")
start = time.time()
targets = collect_targets(soup)
end = time.time()
print(f"Collected {len(targets)} targets in {end - start:.2f} seconds")

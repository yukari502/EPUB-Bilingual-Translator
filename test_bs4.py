from bs4 import BeautifulSoup

html = """
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body>
    <p>Hello</p>
    <div class="paragraph">World</div>
</body>
</html>
"""

soup = BeautifulSoup(html, "xml")
print("soup:", soup)
print("p:", len(soup.find_all("p")))
print("div:", len(soup.find_all("div")))
print("all:", [t.name for t in soup.find_all()])


"""Verify preservation, canonical URLs, internal navigation and sitemap coverage."""
from build import BASE, ROOT, OUT, build, plain
from html.parser import HTMLParser
from html import escape
import re
import xml.etree.ElementTree as ET


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(v for k, v in attrs if k == 'href')


entries = build()
home = (OUT / 'index.html').read_text()
source = (ROOT / 'index.html').read_text()
home_articles = re.findall(r'<article\b[^>]*>.*?</article>',
                           re.sub(r'<!--.*?-->', '', home, flags=re.S), re.S)
assert len(home_articles) == len(entries)
for (number, title, description, article), home_article in zip(entries, home_articles):
    page = (OUT / number / 'index.html').read_text()
    # Individual pages preserve the entire original article byte for byte.
    assert article in page, number
    assert plain(article) == plain(home_article), number
    assert f'href="/{number}/"' in home_article, number
    assert f'<link rel="canonical" href="{BASE}{number}/">' in page, number
    assert '一覧に戻る' not in page, number
    assert 'href="/archive/"' not in page, number
    expected_title = escape(number + ' ' + title + ' | obatahi', quote=True)
    assert '<title>' + expected_title + '</title>' in page, number
    assert f'<meta property="og:title" content="{expected_title}">' in page, number
    assert f'<meta property="og:url" content="{BASE}{number}/">' in page, number
    assert len(re.findall(r'<article\b', page)) == 1, number
    assert 'noindex' not in page.lower(), number
    parser = Links()
    parser.feed(page)
    for href in parser.urls:
        if href.startswith('/'):
            path, _, fragment = href.partition('#')
            target = OUT / path.lstrip('/')
            if path.endswith('/'):
                target = target / 'index.html'
            assert target.exists(), href
            if fragment:
                assert f'id="{fragment}"' in target.read_text(), href

urls = {node.text for node in ET.parse(OUT / 'sitemap.xml').iter()
        if node.tag.endswith('}loc')}
assert urls == {BASE, BASE + 'archive/'} | {BASE + number + '/' for number, *_ in entries}
assert (OUT / 'nehan/index.html').read_bytes() == (ROOT / 'nehan/index.html').read_bytes()
assert source.split('</head>', 1)[1].split('<main>', 1)[0] == home.split('</head>', 1)[1].split('<main>', 1)[0]
assert source.split('</main>', 1)[1] == home.split('</main>', 1)[1]
assert 'Sitemap: ' + BASE + 'sitemap.xml' in (OUT / 'robots.txt').read_text()
assert '<meta name="robots" content="noindex">' in (OUT / 'write/index.html').read_text()
assert BASE + 'write/' not in urls
print('Verified: all original entries, visible text, design, canonical URLs, links and sitemap coverage.')

archive = (OUT / 'archive/index.html').read_text()
assert f'<link rel="canonical" href="{BASE}archive/">' in archive
assert 'href="/archive/"' in home
rows = re.findall(r'<li>(.*?)</li>', archive, re.S)
assert len(rows) == len(entries)
for row, (number, title, _, article) in zip(rows, entries):
    date = re.search(r'<span>(\d{4}\.\d{2}\.\d{2})</span>', article)[1]
    assert f'href="/{number}/"' in row
    assert plain(row) == number + date + title
assert '<article' not in archive
print('Verified: archive order, dates, titles and links for every entry.')

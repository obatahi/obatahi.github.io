"""Build crawlable pages from the existing, unmodified index.html. No dependencies."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_site'
BASE = 'https://obatahi.com/'


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(markup):
    parser = Text()
    parser.feed(markup)
    return ''.join(parser.parts).strip()


def build():
    source = (ROOT / 'index.html').read_text()
    # Commented authoring templates must not become duplicate entries.
    clean = re.sub(r'<!--.*?-->', '', source, flags=re.S)
    articles = re.findall(r'<article\b[^>]*>.*?</article>', clean, re.S)
    if not articles:
        raise ValueError('No entries found; refusing to publish an empty site')
    entries = []
    seen = set()
    for article in articles:
        match = re.search(r'\bid="(\d+)"', article.split('>', 1)[0])
        if not match or match[1] in seen:
            raise ValueError('Missing or duplicate entry number')
        number = match[1]
        seen.add(number)
        label_match = re.search(r'<span class="no">(.*?)</span>', article, re.S)
        if not label_match or plain(label_match[1]) != 'No. ' + number:
            raise ValueError('Entry number does not match its ID: ' + number)
        title_match = re.search(r'<h2\b[^>]*>(.*?)</h2>', article, re.S)
        title = plain(title_match[1]) if title_match else '本日停止'
        paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', article, re.S)
        description = ' '.join(plain(p) for p in paragraphs)[:160]
        entries.append((number, title, description, article))

    head = re.sub(r'[ \t]+$', '', source.split('</head>', 1)[0], flags=re.M)
    footer = re.sub(r'[ \t]+$', '', source.split('</main>', 1)[1], flags=re.M)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for name in ('CNAME', 'favicon.ico', 'favicon.svg', 'apple-touch-icon.png'):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copytree(ROOT / 'nehan', OUT / 'nehan')
    (OUT / '.nojekyll').touch()

    home = source
    for number, title, description, article in entries:
        linked = re.sub(r'<span class="no">.*?</span>',
                        lambda _: '<span class="no"><a href="/' + number
                        + '/" style="color:inherit;border-bottom:none">No. '
                        + number + '</a></span>', article, count=1, flags=re.S)
        home = home.replace(article, linked, 1)
        page_head = re.sub(r'<title>.*?</title>',
                           lambda _: '<title>' + escape(number + ' ' + title + '｜obatahi') + '</title>',
                           head, count=1, flags=re.S)
        page_head = re.sub(r'<meta name="description"[^>]*>',
                           lambda _: '<meta name="description" content="' + escape(description, quote=True) + '">',
                           page_head, count=1)
        page_head = re.sub(r'<link rel="canonical"[^>]*>',
                           lambda _: '<link rel="canonical" href="' + BASE + number + '/">',
                           page_head, count=1)
        page = (page_head + '</head>\n<body>\n<div class="sheet">\n'
                '<header class="masthead"><h1><a href="/">obatahi</a></h1></header>\n'
                '<main>\n' + article + '\n</main>\n'
                '<nav aria-label="一覧"><a href="/#' + number + '">一覧に戻る</a></nav>\n'
                + footer)
        folder = OUT / number
        folder.mkdir()
        (folder / 'index.html').write_text(page)
    (OUT / 'index.html').write_text(home)

    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    sitemap = ET.Element('{' + namespace + '}urlset')
    for url in [BASE] + [BASE + entry[0] + '/' for entry in entries]:
        item = ET.SubElement(sitemap, '{' + namespace + '}url')
        ET.SubElement(item, '{' + namespace + '}loc').text = url
    ET.ElementTree(sitemap).write(OUT / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (OUT / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + BASE + 'sitemap.xml\n')
    print(f'Built {len(entries)} individual pages and {len(entries) + 1} sitemap URLs in {OUT}')
    return entries


if __name__ == '__main__':
    build()

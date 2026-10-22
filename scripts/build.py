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


def sharing(head, title, description, url, kind):
    # Keep metadata consistent even when authoring from previously generated HTML.
    head = re.sub(r'<meta\b[^>]*(?:property|name)=["\'](?:og:|twitter:)[^>]*>\s*', '', head)
    values = [('property', 'og:type', kind), ('property', 'og:locale', 'ja_JP'),
              ('property', 'og:site_name', 'obatahi'), ('property', 'og:title', title),
              ('property', 'og:description', description), ('property', 'og:url', url),
              ('name', 'twitter:card', 'summary'), ('name', 'twitter:title', title),
              ('name', 'twitter:description', description)]
    return head + '\n' + '\n'.join(
        f'<meta {attribute}="{name}" content="{escape(value, quote=True)}">'
        for attribute, name, value in values) + '\n'


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
    footer = re.sub(r'    <span class="archive-link">.*?</span>\n', '', footer)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for name in ('CNAME', 'favicon.ico', 'favicon.svg', 'apple-touch-icon.png'):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copytree(ROOT / 'nehan', OUT / 'nehan')
    shutil.copytree(ROOT / 'write', OUT / 'write')
    (OUT / '.nojekyll').touch()

    home = source
    for number, title, description, article in entries:
        linked = re.sub(r'<span class="no">.*?</span>',
                        lambda _: '<span class="no"><a href="/' + number
                        + '/" style="color:inherit;border-bottom:none">No. '
                        + number + '</a></span>', article, count=1, flags=re.S)
        home = home.replace(article, linked, 1)
        page_head = re.sub(r'<title>.*?</title>',
                           lambda _: '<title>' + escape(number + ' ' + title + ' | obatahi') + '</title>',
                           head, count=1, flags=re.S)
        page_head = re.sub(r'<meta name="description"[^>]*>',
                           lambda _: '<meta name="description" content="' + escape(description, quote=True) + '">',
                           page_head, count=1)
        page_head = re.sub(r'<link rel="canonical"[^>]*>',
                           lambda _: '<link rel="canonical" href="' + BASE + number + '/">',
                           page_head, count=1)
        page_head = sharing(page_head, number + ' ' + title + ' | obatahi', description,
                            BASE + number + '/', 'article')
        page = (page_head + '</head>\n<body>\n<div class="sheet">\n'
                '<header class="masthead"><h1><a href="https://obatahi.com/">obatahi</a></h1></header>\n'
                '<main>\n' + article + '\n</main>\n'
                + footer)
        folder = OUT / number
        folder.mkdir()
        (folder / 'index.html').write_text(page)
    home_head, home_body = home.split('</head>', 1)
    home_title = plain(re.search(r'<title>(.*?)</title>', home_head, re.S)[1])
    home_description = re.search(r'<meta name="description" content="([^"]*)"', home_head)[1]
    (OUT / 'index.html').write_text(sharing(home_head, home_title, plain(home_description),
                                          BASE, 'website') + '</head>' + home_body)

    archive_head = re.sub(r'<title>.*?</title>', '<title>一覧 | obatahi</title>', head, count=1, flags=re.S)
    archive_head = re.sub(r'<meta name="description"[^>]*>',
                          '<meta name="description" content="番号・日付・題から、一日一単位を辿る。">', archive_head, count=1)
    archive_head = re.sub(r'<link rel="canonical"[^>]*>',
                          '<link rel="canonical" href="' + BASE + 'archive/">', archive_head, count=1)
    archive_head = sharing(archive_head, '一覧 | obatahi', '番号・日付・題から、一日一単位を辿る。',
                           BASE + 'archive/', 'website')
    archive_head += """<style>
.archive-title { font-size: 16px; font-weight: 400; margin: 0 0 2.5em; }
.archive-list { list-style: none; margin: 0; padding: 0; }
.archive-list li { border-bottom: 1px solid rgba(22,36,27,.12); }
.archive-list a { display: grid; grid-template-columns: 3em 7em minmax(0,1fr); gap: 1em;
  align-items: baseline; padding: 1em 0; min-height: 44px; box-sizing: border-box;
  color: inherit; border: none; text-decoration: none; }
.archive-list .archive-number, .archive-list time { font-family: "Helvetica Neue",Arial,sans-serif;
  font-size: 11px; letter-spacing: .08em; color: var(--moss); }
.archive-list a:focus-visible { outline: 2px solid var(--moss); outline-offset: 4px; }
.archive-list a:hover { color: var(--moss); }
@media (max-width: 640px) {
  .archive-list a { grid-template-columns: 3em minmax(0,1fr); gap: .4em 1em; }
  .archive-list .archive-name { grid-column: 2; }
}
</style>
"""
    rows = []
    for number, title, description, article in entries:
        date_match = re.search(r'<span>(\d{4}\.\d{2}\.\d{2})</span>', article)
        if not date_match:
            raise ValueError('Missing entry date: ' + number)
        date = date_match[1]
        rows.append(f'<li><a href="/{number}/"><span class="archive-number">{number}</span>'
                    f'<time datetime="{date.replace(".", "-")}">{date}</time>'
                    f'<span class="archive-name">{escape(title)}</span></a></li>')
    (OUT / 'archive').mkdir()
    (OUT / 'archive/index.html').write_text(
        archive_head + '</head>\n<body>\n<div class="sheet">\n'
        '<header class="masthead"><h1><a href="https://obatahi.com/">obatahi</a></h1></header>\n'
        '<main><h2 class="archive-title">一覧</h2>\n<ol class="archive-list">\n'
        + '\n'.join(rows) + '\n</ol></main>\n' + footer)

    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    sitemap = ET.Element('{' + namespace + '}urlset')
    for url in [BASE, BASE + 'archive/'] + [BASE + entry[0] + '/' for entry in entries]:
        item = ET.SubElement(sitemap, '{' + namespace + '}url')
        ET.SubElement(item, '{' + namespace + '}loc').text = url
    ET.ElementTree(sitemap).write(OUT / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (OUT / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + BASE + 'sitemap.xml\n')
    print(f'Built {len(entries)} individual pages and {len(entries) + 2} sitemap URLs in {OUT}')
    return entries


if __name__ == '__main__':
    build()

import re
import xbmc

CARD_SPLIT_RE = re.compile(r'<div class="b-content__inline_item"', re.S)
DATA_ID_RE = re.compile(r'data-id="(\d+)"')
DATA_URL_RE = re.compile(r'data-url="([^"]+)"')
TITLE_RE = re.compile(r'<div class="b-content__inline_item-link">\s*<a[^>]*>(.*?)</a>', re.S)
MISC_RE = re.compile(r'<div[^>]*>\s*(\d{4}[^<]*)</div>', re.S)
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
TYPE_RE = re.compile(r'<i class="entity">([^<]+)</i>')
YEAR_RE = re.compile(r'(\d{4})(?:\s*-\s*(\.{3}|(\d{4})))?')

LAST_UPDATES_RE = re.compile(
    r'<div[^>]*class="[^"]*b-content__inline_items[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.S,
)

def strip_tags(s):
    return re.sub(r'<[^>]+>', '', s)

def parse_year(misc):
    m = YEAR_RE.search(misc)
    if not m:
        return '', ''
    start = m.group(1)
    end_raw = m.group(2)
    if end_raw == '...':
        return start, '...'
    if m.group(3):
        return start, m.group(3)
    return start, start


def parse_feed(html, base_url):
    items = []
    parts = CARD_SPLIT_RE.split(html)
    for chunk in parts[1:]:
        id_m = DATA_ID_RE.search(chunk)
        url_m = DATA_URL_RE.search(chunk)
        if not id_m or not url_m:
            continue
        body = chunk[:3000]
        title_m = TITLE_RE.search(body)
        misc_m = MISC_RE.search(body)
        img_m = IMG_RE.search(body)
        type_m = TYPE_RE.search(body)

        title = strip_tags(title_m.group(1)).strip() if title_m else ''
        misc = strip_tags(misc_m.group(1)).strip() if misc_m else ''
        thumb = img_m.group(1) if img_m else ''
        kind = type_m.group(1).strip() if type_m else ''

        year_start, year_end = parse_year(misc)
        year = year_start if year_start == year_end else '%s - %s' % (year_start, year_end)

        country = genre = ''
        if misc:
            p = [x.strip() for x in misc.split(',')]
            # убираем год из начала, если он там есть
            if p and YEAR_RE.match(p[0]):
                p = p[1:]
            if p:
                country = p[0]
            if len(p) > 1:
                genre = ', '.join(p[1:])

        href = url_m.group(1)
        items.append({
            'id': id_m.group(1),
            'title': title,
            'url': href if href.startswith('http') else base_url + href,
            'thumb': thumb,
            'year': year,
            'country': country,
            'genre': genre,
            'kind': kind,
            'misc': misc,
        })
    return items

def dedupe(items):
    seen = set()
    out = []
    for i in items:
        if i['id'] in seen:
            continue
        seen.add(i['id'])
        out.append(i)
    return out

def parse_categories(html):
    """Меню категорий из шапки. Возвращает [{'title':..., 'url':...}]."""
    m = re.search(r'<ul[^>]*id="topnav-menu"[^>]*>(.*?)</ul>', html, re.S)
    if not m:
        return []
    menu = m.group(1)
    cats = []
    for a in re.finditer(r'<a[^>]*class="[^"]*b-topnav__item-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', menu, re.S):
        cats.append({
            'url': a.group(1),
            'title': strip_tags(a.group(2)).strip(),
        })
    return cats

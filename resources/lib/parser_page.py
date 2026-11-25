import re
import json


def strip_tags(s):
    return re.sub(r'<[^>]+>', '', s or '')


def first(html, pattern, group=1, default=''):
    m = re.search(pattern, html, re.S)
    if not m:
        return default
    return m.group(group).strip()


def parse_page(html, base_url):
    """Парсит страницу фильма или сериала."""
    result = {
        'post_id': '',
        'title': '',
        'orig_title': '',
        'poster': '',
        'year': '',
        'country': '',
        'genre': '',
        'rating_site': '',
        'rating_imdb': '',
        'rating_kp': '',
        'age': '',
        'duration': '',
        'description': '',
        'translators': [],
        'is_series': False,
        'seasons': [],
    }

    # post_id — по id="post_id"
    result['post_id'] = first(html, r'<input[^>]*id="post_id"[^>]*value="(\d+)"')

    # Название
    result['title'] = strip_tags(first(html, r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>'))

    # Оригинальное название
    result['orig_title'] = strip_tags(
        first(html, r'<div[^>]*class="b-post__origtitle"[^>]*>(.*?)</div>'))

    # Постер
    result['poster'] = first(html, r'<img[^>]*itemprop="image"[^>]*src="([^"]+)"')

    # Год — ссылка /year/XXXX/
    result['year'] = first(html, r'href="[^"]*/year/(\d{4})/?"')

    # Страна — все ссылки /country/.../
    countries = re.findall(r'<a[^>]*href="[^"]*/country/[^"]*"[^>]*>([^<]+)</a>', html)
    result['country'] = ', '.join(c.strip() for c in countries)

    # Жанр — все span itemprop="genre"
    genres = re.findall(r'<span[^>]*itemprop="genre"[^>]*>([^<]+)</span>', html)
    result['genre'] = ', '.join(g.strip() for g in genres)

    # Рейтинги
    result['rating_imdb'] = first(
        html, r'class="b-post__info_rates imdb".*?<span class="bold">([\d.]+)</span>')
    result['rating_kp'] = first(
        html, r'class="b-post__info_rates kp".*?<span class="bold">([\d.]+)</span>')
    result['rating_site'] = first(
        html, r'id="rating-layer-num-\d+"[^>]*itemprop="average"[^>]*>([\d.]+)<')

    # Возраст
    result['age'] = first(html, r'<span class="bold" style="color: #666;">(\d+\+)</span>')

    # Длительность
    result['duration'] = first(html, r'itemprop="duration"[^>]*>(\d+)\s*мин')

    # Описание
    result['description'] = strip_tags(
        first(html, r'<div[^>]*class="b-post__description_text"[^>]*>(.*?)</div>'))

    # Признак сериала — наличие блока серий
    result['is_series'] = bool(re.search(
        r'id="simple-episodes-tabs"|b-simple_episodes__list', html))

    # Переводчики — из ul#translators-list
    tl_match = re.search(
        r'<ul[^>]*id="translators-list"[^>]*>(.*?)</ul>', html, re.S)
    if tl_match:
        tl_block = tl_match.group(1)
        # каждый <li ...>...</li>
        for li in re.finditer(r'<li([^>]*)>(.*?)</li>', tl_block, re.S):
            attrs = li.group(1)
            body = li.group(2)
            tid_m = re.search(r'data-translator_id="(\d+)"', attrs)
            if not tid_m:
                continue
            director_m = re.search(r'data-director="(\d+)"', attrs)
            title_m = re.search(r'title="([^"]*)"', attrs)
            name = title_m.group(1) if title_m else strip_tags(body)
            active = 'active' in attrs
            premium = 'prem' in attrs.lower()
            result['translators'].append({
                'id': tid_m.group(1),
                'name': name.strip(),
                'director': director_m.group(1) if director_m else '0',
                'active': active,
                'premium': premium,
            })

    result['seasons'] = parse_episodes(html)
    if result['seasons']:
        result['is_series'] = True

    return result

def parse_episodes(html):
    """Парсит сезоны и серии сериала."""
    seasons = []
    # сезоны
    seasons_block = re.search(
        r'<ul[^>]*id="simple-seasons-tabs"[^>]*>(.*?)</ul>', html, re.S)
    if seasons_block:
        for li in re.finditer(
                r'<li([^>]*)>(.*?)</li>', seasons_block.group(1), re.S):
            attrs = li.group(1)
            body = li.group(2)
            tab_m = re.search(r'data-tab_id="(\d+)"', attrs)
            if not tab_m:
                continue
            seasons.append({
                'season': tab_m.group(1),
                'title': strip_tags(body).strip(),
                'episodes': [],
            })

    # серии — для каждого сезона свой ul id="simple-episodes-list-N"
    for season in seasons:
        list_re = re.compile(
            r'<ul[^>]*id="simple-episodes-list-%s"[^>]*>(.*?)</ul>'
            % re.escape(season['season']), re.S)
        m = list_re.search(html)
        if not m:
            continue
        for li in re.finditer(
                r'<li([^>]*)>(.*?)</li>', m.group(1), re.S):
            attrs = li.group(1)
            body = li.group(2)
            ep_m = re.search(r'data-episode_id="(\d+)"', attrs)
            if not ep_m:
                continue
            season['episodes'].append({
                'episode': ep_m.group(1),
                'title': strip_tags(body).strip(),
            })

    # если сезоны не нашлись, но серии есть — сделаем один псевдо-сезон
    if not seasons:
        m = re.search(
            r'<ul[^>]*class="b-simple_episodes__list[^"]*"[^>]*>(.*?)</ul>',
            html, re.S)
        if m:
            eps = []
            for li in re.finditer(
                    r'<li([^>]*)>(.*?)</li>', m.group(1), re.S):
                attrs = li.group(1)
                body = li.group(2)
                ep_m = re.search(r'data-episode_id="(\d+)"', attrs)
                if not ep_m:
                    continue
                eps.append({
                    'episode': ep_m.group(1),
                    'title': strip_tags(body).strip(),
                })
            if eps:
                seasons.append({
                    'season': '1',
                    'title': 'Сезон 1',
                    'episodes': eps,
                })

    return seasons

def parse_streams_string(streams_str):
    if not streams_str:
        return []

    # Убираем экранирование слэшей и HTML-теги
    streams_str = streams_str.replace('\\/', '/')
    streams_str = re.sub(r'<[^>]+>', '', streams_str)

    result = []
    # Разбиваем по запятой — это разделитель между разными качествами
    blocks = streams_str.split(',')

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Ищем [качество] в начале блока
        m = re.match(r'^\[([^\]]+)\](.+)$', block)
        if not m:
            continue

        quality = m.group(1).strip()
        rest = m.group(2).strip()

        # Берем первую ссылку до " or "
        # (первая ссылка обычно m3u8, что нам и нужно для Kodi)
        first_url = rest.split(' or ')[0].strip()

        result.append((quality, first_url))

    return result

def parse_streams_from_html(html):
    m = re.search(r'"streams"\s*:\s*"([^"]+)"', html, re.S)
    if not m:
        return []
    return parse_streams_string(m.group(1))

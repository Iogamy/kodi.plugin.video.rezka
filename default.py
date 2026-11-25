import sys
import re
import urllib.parse
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

from resources.lib.rezka_api import RezkaAPI
from resources.lib.parser import parse_feed, dedupe, parse_categories
from resources.lib.cache_manager import FeedCache
from resources.lib.parser_page import parse_page, parse_streams_from_html

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1])
BASE = sys.argv[0]


def build_url(**kwargs):
    return BASE + '?' + urllib.parse.urlencode(kwargs)

def add_item(label, url, is_folder=True, thumb='', info=None):
    li = xbmcgui.ListItem(label=label)
    if thumb:
        li.setArt({'thumb': thumb, 'icon': thumb})
    if info:
        li.setInfo('video', info)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, is_folder)

def build_label(item):
    show_country = ADDON.getSettingBool('show_country')
    show_genre = ADDON.getSettingBool('show_genre')
    label = item['title']
    if item.get('year'):
        label += ' [COLOR=gray](%s)[/COLOR]' % item['year']
    if show_country and item.get('country'):
        label += ' [COLOR=dimgray]· %s[/COLOR]' % item['country']
    if show_genre and item.get('genre'):
        label += ' [COLOR=dimgray]· %s[/COLOR]' % item['genre']
    return label


def build_info(item):
    info = {'title': item.get('title', '')}
    if item.get('genre'):
        info['genre'] = item['genre']
    if item.get('country'):
        info['country'] = item['country']
    if item.get('year'):
        first = item['year'].split(' - ')[0]
        if first.isdigit():
            info['year'] = int(first)
    return info


def render_item(item):
    add_item(
        build_label(item),
        build_url(mode='open', url=item['url']),
        True,
        item.get('thumb', ''),
        build_info(item),
    )


def feed(api, cache):
    r = api.get('/')
    if r.status_code != 200:
        xbmcgui.Dialog().notification('Rezka', 'Ошибка загрузки')
        xbmcplugin.endOfDirectory(HANDLE, False)
        return
    items = dedupe(parse_feed(r.text, api.base_url))[:32]
    if not items:
        xbmcplugin.endOfDirectory(HANDLE, False)
        return
    added = cache.update(items)
    added_ids = {a['id'] for a in added}
    for item in items:
        label_override = None
        if item['id'] in added_ids:
            label_override = '[COLOR=lime]●[/COLOR] ' + build_label(item)
        if label_override:
            add_item(label_override,
                     build_url(mode='open', url=item['url']),
                     True, item.get('thumb', ''), build_info(item))
        else:
            render_item(item)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)


def search(api):
    query = xbmcgui.Dialog().input('Поиск', type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        return
    r = api.get('/search/', params={'do': 'search', 'subaction': 'search', 'q': query})
    items = dedupe(parse_feed(r.text, api.base_url))
    for item in items:
        render_item(item)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)


def category(api, url):
    r = api.get(url)
    items = dedupe(parse_feed(r.text, api.base_url))
    for item in items:
        render_item(item)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)


def open_item(api, url):
    r = api.get(url)
    if r.status_code != 200:
        xbmcgui.Dialog().notification('Rezka', 'Ошибка загрузки')
        xbmcplugin.endOfDirectory(HANDLE, False)
        return

    page = parse_page(r.text, api.base_url)
    if not page['post_id']:
        xbmcgui.Dialog().notification('Rezka', 'Не удалось разобрать страницу')
        xbmcplugin.endOfDirectory(HANDLE, False)
        return

    # информация о видео
    info = {
        'title': page['title'],
        'originaltitle': page['orig_title'],
        'plot': page['description'],
        'genre': page['genre'],
        'country': page['country'],
        'rating': page['rating_site'] or page['rating_imdb'],
    }
    if page['year'].isdigit():
        info['year'] = int(page['year'])
    if page['duration'].isdigit():
        info['duration'] = int(page['duration']) * 60
    if page['age']:
        info['mpaa'] = page['age']

    # выбор переводчика
    translators = page['translators'] or [
        {'id': '0', 'name': 'По умолчанию', 'director': '0',
         'active': True, 'premium': False}]
    active = next((t for t in translators if t['active']), translators[0])

    if len(translators) > 1:
        names = []
        for t in translators:
            mark = ''
            if t['premium']:
                mark = ' [PREMIUM]'
            names.append(t['name'] + mark)
        idx = xbmcgui.Dialog().select(
            'Озвучка', names, preselect=translators.index(active))
        if idx < 0:
            xbmcplugin.endOfDirectory(HANDLE, False)
            return
        chosen = translators[idx]
    else:
        chosen = active

    # если премиум и у нас нет премиума — предупредим
    if chosen['premium']:
        xbmcgui.Dialog().notification(
            'Rezka', 'Эта озвучка доступна только с Premium')

    if page['is_series'] and page['seasons']:
        # сериал: список сезонов → серий
        for season in page['seasons']:
            for ep in season['episodes']:
                label = '%s · %s' % (season['title'], ep['title'])
                item_uri = build_url(
                    mode='play_episode',
                    url=url,
                    post_id=page['post_id'],
                    translator_id=chosen['id'],
                    director=chosen['director'],
                    season=season['season'],
                    episode=ep['episode'],
                    title='%s — %s' % (page['title'], label),
                )
                li = xbmcgui.ListItem(label=label)
                li.setArt({'thumb': page['poster'], 'icon': page['poster']})
                li.setInfo('video', info)
                li.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(HANDLE, item_uri, li, False)
        xbmcplugin.setContent(HANDLE, 'episodes')
    else:
        # фильм: одна кнопка «Смотреть»
        label = '[B]▶ Смотреть (%s)[/B]' % chosen['name']
        item_uri = build_url(
            mode='play',
            url=url,
            post_id=page['post_id'],
            translator_id=chosen['id'],
            director=chosen['director'],
            title=page['title'],
        )
        li = xbmcgui.ListItem(label=label)
        li.setArt({'thumb': page['poster'], 'icon': page['poster']})
        li.setInfo('video', info)
        li.setProperty('IsPlayable', 'true')
        xbmcplugin.addDirectoryItem(HANDLE, item_uri, li, False)
        xbmcplugin.setContent(HANDLE, 'movies')

    # описание — отдельным пунктом
    if page['description']:
        desc_uri = build_url(
            mode='show_desc', text=page['description'], title=page['title'])
        add_item('[I]Описание[/I]', desc_uri, False, page['poster'], info)

    xbmcplugin.endOfDirectory(HANDLE)


def show_desc(text, title):
    xbmcgui.Dialog().textviewer(title, text)
    xbmcplugin.endOfDirectory(HANDLE)

def get_series_streams(api, post_id, translator_id, season, episode):
    """
    Делает POST-запрос к rezka.fi, чтобы получить потоки для конкретной серии.
    Возвращает список кортежей (quality, url).
    """
    url = f'{api.base_url}/ajax/get_cdn_series/'
    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{api.base_url}/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': api.base_url,
    }
    data = {
        'id': post_id,
        'translator_id': translator_id,
        'season': season,
        'episode': episode,
        'action': 'get_stream',
    }
    try:
        r = api.session.post(url, data=data, headers=headers, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except Exception as ex:
        xbmc.log(f'Rezka: series stream request failed: {ex}', xbmc.LOGERROR)
        return []

    # В ответе payload['url'] содержит строку со ссылками (как в фильме)
    streams_str = payload.get('url', '')
    if not streams_str:
        return []

    # Дальше используем ту же логику парсинга, что и для фильма
    # (можно вынести её в отдельную функцию parse_streams_string)
    from resources.lib.parser_page import parse_streams_string
    return parse_streams_string(streams_str)

def get_stream_url(api, post_id, translator_id, season, episode, is_movie=True):
    url = f'{api.base_url}/ajax/get_cdn_series/'
    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{api.base_url}/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': api.base_url,
    }
    data = {
        'id': post_id,
        'translator_id': translator_id,
        'season': season,
        'episode': episode,
        'action': 'get_movie' if is_movie else 'get_stream',
    }
    try:
        r = api.session.post(url, data=data, headers=headers, timeout=30)
        r.raise_for_status()
        payload = r.json()
        xbmc.log('Rezka: RAW JSON from server: %s' % payload, xbmc.LOGINFO)  # ← ЛОГ
    except Exception as ex:
        xbmc.log(f'Rezka: stream request failed: {ex}', xbmc.LOGERROR)
        return []

    streams_str = payload.get('url', '')
    xbmc.log('Rezka: streams_str = %s' % streams_str, xbmc.LOGINFO)  # ← ЛОГ
    if not streams_str:
        xbmc.log(f'Rezka: no url in response: {payload}', xbmc.LOGERROR)
        return []

    from resources.lib.parser_page import parse_streams_string
    result = parse_streams_string(streams_str)
    xbmc.log('Rezka: parsed streams = %s' % result, xbmc.LOGINFO)  # ← ЛОГ
    return result


def select_quality_and_play(streams, title, api, chosen_quality=None):
    """
    streams: список кортежей (quality, url)
    chosen_quality: строка из настроек (например, "720p" или "Спрашивать каждый раз")
    """
    if not streams:
        xbmcgui.Dialog().notification('Rezka', 'Не удалось получить потоки')
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    # Сортируем по качеству (по числам в строке)
    def q_key(item):
        q = item[0].lower()
        m = re.search(r'(\d+)', q)
        return int(m.group(1)) if m else 0
    streams.sort(key=q_key, reverse=True)

    chosen_url = None

    # Если пользователь задал качество в настройках (не "Спрашивать каждый раз")
    if chosen_quality and chosen_quality != 'Спрашивать каждый раз':
        for q, u in streams:
            if q.lower() == chosen_quality.lower():
                chosen_url = u
                break

    # Если качество не задано или не нашли — показываем диалог
    if chosen_url is None:
        names = [s[0] for s in streams]
        idx = xbmcgui.Dialog().select('Выберите качество', names)
        if idx < 0:
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        chosen_url = streams[idx][1]

    # Отдаём в Kodi
    li = xbmcgui.ListItem(path=chosen_url)
    li.setInfo('video', {'title': title})
    li.setMimeType('application/vnd.apple.mpegurl')
    li.setProperty('inputstream', 'inputstream.adaptive')
    li.setProperty('inputstream.adaptive.manifest_type', 'hls')
    li.setProperty('inputstream.adaptive.stream_headers',
                   'User-Agent=Mozilla/5.0&Referer=%s/&Origin=%s' % (api.base_url, api.base_url))
    xbmcplugin.setResolvedUrl(HANDLE, True, li)

def play(api, url, post_id, translator_id, director, title):
    streams = get_stream_url(api, post_id, translator_id, 0, 0, is_movie=True)

    # Читаем настройку как индекс
    quality_index = ADDON.getSettingInt('default_quality')
    quality_values = ["Спрашивать каждый раз", "360p", "480p", "720p", "1080p", "1080p Ultra", "2K", "4K"]
    chosen_quality = quality_values[quality_index] if 0 <= quality_index < len(quality_values) else "Спрашивать каждый раз"

    select_quality_and_play(streams, title, api, chosen_quality)


def play_episode(api, url, post_id, translator_id, director, season, episode, title):
    streams = get_stream_url(api, post_id, translator_id, season, episode, is_movie=False)

    quality_index = ADDON.getSettingInt('default_quality')
    quality_values = ["Спрашивать каждый раз", "360p", "480p", "720p", "1080p", "1080p Ultra", "2K", "4K"]
    chosen_quality = quality_values[quality_index] if 0 <= quality_index < len(quality_values) else "Спрашивать каждый раз"

    select_quality_and_play(streams, title, api, chosen_quality)

def menu():
    add_item('[B]Последние поступления[/B]', build_url(mode='feed'))
    add_item('[B]Поиск[/B]', build_url(mode='search'))
    # add_item('[B]Категории[/B]', build_url(mode='categories'))
    xbmcplugin.endOfDirectory(HANDLE)

def router():
    params = urllib.parse.parse_qs(sys.argv[2][1:])
    mode = params.get('mode', ['main'])[0]
    url = params.get('url', [None])[0]

    try:
        api = RezkaAPI()
        cache = FeedCache()
    except Exception as ex:
        xbmc.log('Rezka: init failed: %s' % ex, xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rezka', 'Ошибка инициализации: %s' % ex)
        return

    if mode == 'main':
        menu()
    elif mode == 'feed':
        feed(api, cache)
    elif mode == 'search':
        search(api)
    elif mode == 'categories':
        categories(api)
    elif mode == 'category':
        category(api, url)
    elif mode == 'open':
        open_item(api, url)
    elif mode == 'play':
        play(api, url,
             params.get('post_id', [''])[0],
             params.get('translator_id', [''])[0],
             params.get('director', ['0'])[0],
             params.get('title', [''])[0])
    elif mode == 'play_episode':
        play_episode(
            api, url,
            params.get('post_id', [''])[0],
            params.get('translator_id', [''])[0],
            params.get('director', ['0'])[0],
            params.get('season', ['1'])[0],
            params.get('episode', ['1'])[0],
            params.get('title', [''])[0])
    elif mode == 'show_desc':
        show_desc(params.get('text', [''])[0], params.get('title', [''])[0])
    else:
        menu()


if __name__ == '__main__':
    router()

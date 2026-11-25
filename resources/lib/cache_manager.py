import json
import os
import time
import xbmc
import xbmcaddon
import xbmcvfs

class FeedCache:
    FILE = 'feed_cache.json'
    NEW_TTL = 24 * 3600  # «новое» = появилось за последние 24 часа

    def __init__(self):
        addon = xbmcaddon.Addon()
        self.profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        os.makedirs(self.profile, exist_ok=True)
        self.path = os.path.join(self.profile, self.FILE)

    def load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # чистим элементы без first_seen (legacy)
            return [i for i in data if isinstance(i, dict) and 'first_seen' in i]
        except Exception as ex:
            xbmc.log('FeedCache load failed: %s' % ex, xbmc.LOGWARNING)
            return []

    def save(self, items):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            xbmc.log('FeedCache save failed: %s' % ex, xbmc.LOGWARNING)

    def update(self, new_items):
        old = self.load()
        now = int(time.time())
        old_by_id = {i['id']: i for i in old}
        for item in new_items:
            prev = old_by_id.get(item['id'])
            item['first_seen'] = prev.get('first_seen', now) if prev else now
        self.save(new_items)
        added = [i for i in new_items if now - i['first_seen'] < self.NEW_TTL]
        xbmc.log('FeedCache: added=%d total=%d' % (len(added), len(new_items)), xbmc.LOGINFO)
        return added

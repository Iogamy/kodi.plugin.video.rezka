import json
import os
import time
import requests
import xbmc
import xbmcaddon
import xbmcvfs


class RezkaAPI:
    SESSION_FILE = 'session.json'
    SESSION_TTL = 24 * 3600

    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.base_url = self.addon.getSetting('base_url').rstrip('/') or 'https://rezka.fi'
        self.profile = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        self.session_path = os.path.join(self.profile, self.SESSION_FILE)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0 Safari/537.36',
            'Referer': self.base_url + '/',
        })
        self._load_session()
        self._ensure_logged_in()

    def _load_session(self):
        if not os.path.exists(self.session_path):
            return
        try:
            with open(self.session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if time.time() - data.get('ts', 0) > self.SESSION_TTL:
                return
            for name, value in data.get('cookies', {}).items():
                self.session.cookies.set(name, value)
            xbmc.log('Rezka: session loaded (%d cookies)' % len(self.session.cookies), xbmc.LOGINFO)
        except Exception as ex:
            xbmc.log('Rezka: load session failed: %s' % ex, xbmc.LOGWARNING)

    def _save_session(self):
        try:
            os.makedirs(self.profile, exist_ok=True)
            data = {
                'ts': int(time.time()),
                'cookies': {c.name: c.value for c in self.session.cookies},
            }
            with open(self.session_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            try:
                os.chmod(self.session_path, 0o600)
            except Exception:
                pass
            xbmc.log('Rezka: session saved', xbmc.LOGINFO)
        except Exception as ex:
            xbmc.log('Rezka: save session failed: %s' % ex, xbmc.LOGWARNING)

    def _is_logged_in_html(self, html):
        return ('dle_user_id' in str(dict(self.session.cookies))
                and 'login_name' not in html
                and '/logout/' in html)

    def _ensure_logged_in(self):
        if self.session.cookies:
            try:
                r = self.session.get(self.base_url + '/', timeout=30)
                if self._is_logged_in_html(r.text):
                    xbmc.log('Rezka: already logged in', xbmc.LOGINFO)
                    return
            except Exception as ex:
                xbmc.log('Rezka: check session failed: %s' % ex, xbmc.LOGWARNING)

        email = self.addon.getSetting('email')
        password = self.addon.getSetting('password')
        if not email or not password:
            xbmc.log('Rezka: credentials not set', xbmc.LOGERROR)
            return

        self.session.get(self.base_url + '/', timeout=30)

        r = self.session.post(
            self.base_url + '/ajax/login/',
            data={
                'login_name': email,
                'login_password': password,
                'login_not_save': '0',
            },
            headers={'X-Requested-With': 'XMLHttpRequest'},
            timeout=30,
        )
        try:
            payload = r.json()
        except ValueError:
            xbmc.log('Rezka: login non-json: %s' % r.text[:200], xbmc.LOGERROR)
            return

        if not payload.get('success'):
            if 'logged_email' in payload:
                xbmc.log('Rezka: already logged in (server)', xbmc.LOGINFO)
                self._save_session()
                return
            xbmc.log('Rezka: login failed: %s' % payload, xbmc.LOGERROR)
            return

        self.session.get(self.base_url + '/', timeout=30)
        self._save_session()
        xbmc.log('Rezka: login OK, cookies: %s' % list(self.session.cookies.keys()), xbmc.LOGINFO)

    def get(self, path, **kwargs):
        kwargs.setdefault('timeout', 30)
        if path.startswith('http://') or path.startswith('https://'):
            return self.session.get(path, **kwargs)
        return self.session.get(self.base_url + path, **kwargs)

    def post(self, path, **kwargs):
        kwargs.setdefault('timeout', 30)
        if path.startswith('http://') or path.startswith('https://'):
            return self.session.post(path, **kwargs)
        return self.session.post(self.base_url + path, **kwargs)

# -*- coding: utf-8 -*-
import os
import sys
import io
import time
import threading
from datetime import datetime as dt, timedelta as td, timezone as tz
import webbrowser
import re

import schedule
from pystray import Icon, Menu, MenuItem
from PIL import Image
import requests
from bs4 import BeautifulSoup
from win11toast import notify
from tenacity import retry, stop_after_attempt, wait_fixed

TITLE = 'Astoltia Defense Force'
tokoyami_url = 'https://hiroba.dqx.jp/sc/tokoyami/#raid-container'
tengoku_url = 'https://hiroba.dqx.jp/sc/game/tengoku'
MAX_MENUS = 6
# 新兵団がきたら手動更新
titles = {
    "2": "闇朱の獣牙兵団",
    "3": "紫炎の鉄機兵団",
    "4": "深碧の造魔兵団",
    "6": "蒼怨の屍獄兵団",
    "8": "銀甲の凶蟲兵団",
    "9": "翠煙の海妖兵団",
    "10": "灰塵の竜鱗兵団",
    "11": "彩虹の粘塊兵団",
    "12": "芳墨の華烈兵団",
    "13": "白雲の冥翼兵団",
    "14": "腐緑の樹葬兵団",
    "15": "青鮮の菜果兵団",
    "16": "鋼塊の重滅兵団",
    "19": "全兵団",
}
# 源世庫: 新ボスがきたら手動更新
panigarms = {
    '3c82883f10a11f98a66cc966323d82ea': '源世鳥アルマナ',
    'ce3cc47d714c3eb7289ed998f1352e13': 'じげんりゅう',
    '5cb0b2118fa73de5802ac2af343b1788': '源世妃フォルダイナ',
    'efab9b7fb5df0cb759999325b02b2043': '鉄巨兵ダイダルモス',
    '614575237b24bfbd81bd68ff5e5ff922': 'パニガキャッチャー',
    '5':                                '源世果フルポティ',
    '6':                                '魔妖星プルタヌス',
    'e418865d407684f7a570a4563704b5d3': '堕天使エルギオス',
}
NEXT_PANIGARM = 3       # days


def resource_path(path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath('.'), path)


def Dracky(body):
    notify(body, app_id=TITLE, audio=resource_path('Assets/nc308516.mp3'))


class taskTray:
    def __init__(self):
        self.running = False
        self.icon_url = str()
        self.page_cache = {}
        self.metal_cache = []
        self.icon_cache = {}            # { "num": Image }
        self.enableMetal = True
        self.raids = self.initRaids()   # {'tengoku': '', 'inferno': '', 'konmeiko': ''}
        self.panigarm = []              # [start datetime, hashkey]

        self.updatePage(retry=False)
        if not self.page_cache:
            notify(body='メンテナンス中', app_id=TITLE, duration='long')
            sys.exit(1)

        menu = self.updateMenu()
        self.app = Icon(name='PYTHON.win32.AstoltiaDefenseForce', title=TITLE, menu=menu)
        self.checkMetal()
        self.doCheck(wait=False)

    def initRaids(self):
        return {
            'tengoku': str(),
            'inferno': str(),
            'konmeiko': str(),
        }

    def getNow(self, fmt='%H:%M:%S'):
        return dt.now(tz(td(hours=+9), 'JST')).strftime(fmt)

    def getNowHalf(self):
        hh, mm = self.getNow('%H:%M').split(':')
        if hh < '06':
            hh = int(hh) + 24
        return f'{hh:02}:{mm}'

    def isMetal(self, t0):
        # t0  -> 00:00, 09:00, 11:30, 23:30
        # t1  -> 24:30, 09:30, 12:00, 24:00
        hh, mm = t0.split(':')
        if hh < '06':
            hh = int(hh) + 24
        t0 = f'{hh}:{mm}'
        if t0.endswith('00'):
            t1 = t0.replace(':00', ':30')
        else:
            # :30
            hh = int(t0.split(':')[0]) + 1
            t1 = f'{hh:02}:00'

        hhmm = self.getNowHalf()
        return t0 <= hhmm < t1

    def isOverMetal(self, t0):
        # t0  -> 00:00, 06:00, 09:00, 11:30, 23:30, 02:30, 05:00, 05:30
        # t1  -> 24:30, 06:30, 09:30, 12:00, 24:00, 27:00, 29:30, 30:00
        hh = int(t0.split(':')[0])
        if t0.endswith('00'):
            mm = 30
        else:
            hh += 1
            mm = 0

        if 0 <= hh <= 6:
            if hh != 6 or mm != 30:
                hh += 24

        t1 = f'{hh:02}:{mm:02}'
        hhmm = self.getNowHalf()
        return hhmm >= t1

    def getTarget(self, image_url):
        return image_url.split('/')[-1].split('.')[0]

    def doOpen(self):
        self.updatePage(retry=False)
        self.doCheck(wait=False)
        webbrowser.open(tokoyami_url)

    def updateMenu(self):
        now = self.getNow('%H:00')
        item = [
            MenuItem('Open', self.doOpen, default=True, visible=False),
            MenuItem('Check Metal Rookies', self.toggleMetal, checked=lambda _: self.enableMetal),
            Menu.SEPARATOR,
        ]

        # metal rookies
        if self.enableMetal:
            idx = 0
            for t in self.metal_cache:
                # 現在以前はスキップ
                if self.isOverMetal(t):
                    continue

                item.append(MenuItem(f'{t} メタルーキー', lambda _: False, checked=lambda x: self.isMetal(str(x).split()[0])))
                idx += 1
                if idx >= MAX_MENUS:
                    break
            item.append(Menu.SEPARATOR)

        # defense force
        matched = False
        idx = 0
        for t in self.page_cache:
            # 現在以前はスキップ
            if t == now:
                matched = True
            if not matched:
                continue

            target = self.getTarget(self.page_cache[t])
            item.append(MenuItem(f'{t} {titles[target]}', lambda _: False, checked=lambda x: str(x).split()[0] == now))
            idx += 1
            if idx >= MAX_MENUS:
                break
        item.append(Menu.SEPARATOR)

        # 天獄・インフェルノ・昏冥庫
        # yyyy/mm/dd hh:59 まで {target}
        for key in self.raids:
            if self.raids[key]:
                item.append(MenuItem(f'{self.raids[key]}', lambda _: False, checked=lambda _: True))
        if any(self.raids.values()):
            item.append(Menu.SEPARATOR)

        # panigarm
        sdate, key = self.panigarm
        for idx, _key in enumerate(panigarms):
            if _key == key:
                break
        nxt = (idx + 1) % len(panigarms)
        lst = list(panigarms)
        espan = (sdate + td(days=NEXT_PANIGARM, hours=5, minutes=59)).strftime('%Y/%m/%d %H:%M まで')
        nspan = (sdate + td(days=NEXT_PANIGARM, hours=6)).strftime('%Y/%m/%d %H:%M から')
        item.append(MenuItem(f'{espan} {panigarms.get(key, key)}', lambda _: False, checked=lambda _: True))
        item.append(MenuItem(f'{nspan} {panigarms[lst[nxt]]}', lambda _: False, checked=lambda _: False))

        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Exit', self.stopApp))
        return Menu(*item)

    def makeIconCache(self):
        def _makeIconImage(icon_url):
            with requests.get(icon_url) as r:
                image = Image.open(io.BytesIO(r.content))
                w, h = image.size
                # crop center
                icon_image = image.crop(((w - h) // 2, 0, (w + h) // 2, h)).resize((16, 16))
                return icon_image

        # 防衛軍
        for t in self.page_cache:
            icon_url = self.page_cache[t]
            target = self.getTarget(icon_url)
            if target not in self.icon_cache:
                self.icon_cache[target] = _makeIconImage(icon_url)

        # メタルーキー(メタルスライム)
        icon_url = 'https://cache.hiroba.dqx.jp/dq_resource/img/tokoyami/koushin/ico/1.png'
        if '1' not in self.icon_cache:
            self.icon_cache['1'] = _makeIconImage(icon_url)

    def getIcon(self, icons):
        if self.enableMetal:
            for t in self.metal_cache:
                if self.isMetal(t):
                    # 1秒毎に返すアイコンが異なる感じ
                    second = int(self.getNow('%S'))
                    return icons[second % 2]

        return icons[0]

    def updateIcon(self, update_menu=True):
        target = self.getTarget(self.icon_url)
        icon_adf = self.icon_cache[target]
        icon_metal = self.icon_cache['1']
        self.app.icon = self.getIcon([icon_adf, icon_metal])
        if update_menu:
            self.app.update_menu()

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(1))
    def updatePage(self, retry=True):
        """
        毎日 6:00 に更新
        """
        now = self.getNow('%m/%d')
        print('>>>', self.getNow())

        with requests.get(tokoyami_url, timeout=10) as r:
            soup = BeautifulSoup(r.content, 'html.parser')
            tables = soup.find_all('table', class_='tokoyami-raid')
            if tables:
                # 同じクラスでメタルーキーもあるので先頭だけ
                trs = tables[0].find_all('tr')
                # 日付が一致しているか
                if retry and not trs[0].find_all('th')[1].text.strip().startswith(now):
                    raise Exception('date not match')
                print('<<<')

                for tr in trs:
                    tds = tr.find_all('td')
                    # th のときは td がないのでスキップ
                    if len(tds) == 0:
                        continue

                    hh, _ = tds[0].contents[0].strip().split('\xa0')[0].split(':')
                    _time = f'{int(hh):02}:00'
                    icon_url = tds[1].contents[1].get('src')
                    self.page_cache[_time] = icon_url

                # metal rookies
                self.metal_cache = []
                trs = tables[1].find_all('tr')
                for tr in trs:
                    tds = tr.find_all('td')
                    # th のときは td がないのでスキップ
                    if len(tds) == 0:
                        continue

                    if tds[1].find('img'):
                        hh, mm = tds[0].contents[0].strip().split('\xa0')[0].split(':')
                        _time = f'{int(hh):02}:{mm}'
                        self.metal_cache.append(_time)

                # panigarm
                panigarm = soup.find_all(class_='mt20')[-1]
                key = panigarm.find('img').get('src').split('/')[-1].split('.')[0]
                start = re.sub(r'（.）', '', panigarm.find('div', class_='mt12').text).strip().split('\xa0')[0]
                nums_re = re.compile(r'(?a)(\d+)')
                yyyy, mm, dd, _, _ = re.findall(nums_re, start)
                sdate = dt(year=int(yyyy), month=int(mm), day=int(dd))
                self.panigarm = [sdate, key]

                # update icon cache
                self.makeIconCache()

            print(self.getNow(), tokoyami_url, 'updated')

    def doCheck(self, wait=True):
        """
        毎正時に更新
        """
        if wait:
            time.sleep(1)

        now = self.getNow('%H:00')

        # バトルコンテンツ出現情報
        with requests.get(tengoku_url, timeout=10) as r:
            self.raids = self.initRaids()
            soup = BeautifulSoup(r.content, 'html.parser')
            # 天獄
            # 'tengoku mt15 is-open' ?
            # span =
            # target =
            self.raids['tengoku'] = '2025/02/16 04:59 まで 暴虐の幻影神'

            # インフェルノ
            # 'f-inferno mt20 is-open' ?
            inferno = soup.find(class_='inferno mt20 is-open')
            if inferno:
                print(inferno)
                # span = inferno.find(class_='f-inferno-period')
                # target = inferno.
            self.raids['inferno'] = '2025/02/14 11:59 まで ダークキング'

            # 昏冥庫
            konmeiko = soup.find(class_='konmeiko mt20 is-open')
            if konmeiko:
                span = konmeiko.find(class_='konmeiko-period').text.strip().split('\n')[-1].strip()
                target = konmeiko.find(class_='konmeiko-target-label').text.strip()
                self.raids['konmeiko'] = f'{span} {target}'

            print(self.getNow(), tengoku_url, 'updated')

        # つよさ予報の内容に更新
        icon_url = self.page_cache.get(now)
        if icon_url is None:
            self.updatePage()
            if not self.page_cache:
                return
            icon_url = self.page_cache.get(now)

        if icon_url != self.icon_url:
            self.icon_url = icon_url

            # set self.app.icon
            self.updateIcon(update_menu=False)
            target = self.getTarget(self.icon_url)
            self.app.title = titles[target]
            self.app.menu = self.updateMenu()
            self.app.update_menu()
            print(self.getNow(), titles[target], 'icon updated')

            if target == '19':
                Dracky(f'{now} {titles[target]}')

    def checkMetal(self):
        """
        :00, :30 にチェック
        """
        self.app.menu = self.updateMenu()
        self.app.update_menu()
        if self.enableMetal:
            for t in self.metal_cache:
                if self.isMetal(t):
                    Dracky(f'{t} メタルーキー軍団 大行進中')

    def toggleMetal(self):
        self.enableMetal = not self.enableMetal
        self.checkMetal()

    def runSchedule(self):
        schedule.every().day.at('06:00').do(self.updatePage)
        schedule.every().hour.at(':00').do(self.doCheck)
        schedule.every().hour.at(':00').do(self.checkMetal)
        schedule.every().hour.at(':30').do(self.checkMetal)
        schedule.every().seconds.do(self.updateIcon)

        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def stopApp(self):
        self.running = False
        self.app.stop()

    def runApp(self):
        self.running = True

        task_thread = threading.Thread(target=self.runSchedule)
        task_thread.start()

        self.app.run()


if __name__ == '__main__':
    taskTray().runApp()

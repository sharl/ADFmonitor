# -*- coding: utf-8 -*-
import sys
import io
import time
import threading
from datetime import datetime as dt, timedelta as td, timezone as tz
import webbrowser
import re
import ctypes
import winsound as ws

import schedule
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw, ImageEnhance
import requests
from bs4 import BeautifulSoup
from win11toast import notify
from tenacity import retry, stop_after_attempt, wait_fixed
import darkdetect as dd

from utils import resource_path
from Badges import Badges

TITLE = 'Astoltia Defense Force'
tokoyami_url = 'https://hiroba.dqx.jp/sc/tokoyami/#raid-container'
tengoku_url = 'https://hiroba.dqx.jp/sc/game/tengoku'
MAX_MENUS = 8
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
    "17": "金神の遺宝兵団",
    "18": "紅爆の暴賊兵団",
    "19": "全兵団",
}
# 紫炎の鉄機兵団, 全兵団
NOTIFICATION_TARGET = ['3', '19']
GOLD = (255, 215, 0)
# 源世庫: 新ボスがきたら手動更新
panigarms = {
    '3c82883f10a11f98a66cc966323d82ea': '源世鳥アルマナ',
    'ce3cc47d714c3eb7289ed998f1352e13': 'じげんりゅう',
    '5cb0b2118fa73de5802ac2af343b1788': '源世妃フォルダイナ',
    'efab9b7fb5df0cb759999325b02b2043': '鉄巨兵ダイダルモス',
    '614575237b24bfbd81bd68ff5e5ff922': 'パニガキャッチャー',
    '5eadbe8cb290e7493cfddf187a8705de': '源世果フルポティ',
    '239253d5c8ce25bb70f11eb97b8bcee6': '魔妖星プルタヌス',
    'e418865d407684f7a570a4563704b5d3': '堕天使エルギオス',
}
NEXT_PANIGARM = 3       # days
NUMS_RE = re.compile(r'(?a)(\d+)')

PreferredAppMode = {
    'Light': 0,
    'Dark': 1,
}
# https://github.com/moses-palmer/pystray/issues/130
ctypes.windll['uxtheme.dll'][135](PreferredAppMode[dd.theme()])


def Dracky(body):
    notify(body, app_id=TITLE, audio={'silent': 'true'})
    ws.PlaySound(resource_path('Assets/nc308516m.wav'), ws.SND_FILENAME)


class taskTray:
    def __init__(self):
        self.running = False
        self.icon_url = str()
        self.page_cache = {}
        self.metal_cache = []
        self.icon_cache = {}            # { "num": Image }
        self.badge_cache = {}
        self.enableMetal = True
        self.nowMetal = False
        self.raids = self.initRaids()   # {'tengoku': '', 'inferno': '', 'pani': '', 'ikai': ''}
        self.xclass = {
            'inferno': 'f-inferno',
            'pani': 'konmeiko',
        }
        self.xnames = {
            'pani': 'konmeiko',
        }
        self.panigarm = []              # [start datetime, hashkey]

        # バッジ周り初期化
        self.show_badges = False
        self.raidLabel = {
            'tengoku': '邪神の宮殿 天獄',
            'inferno': 'フェスタ・インフェルノ',
            'pani': '昏冥庫パニガルム',
            'ikai': '異界の創造主',
        }
        self.select_badges = {}
        # サブメニュー登録
        self.badge_submenu = []
        for _badge in self.raids:
            self.select_badges[self.raidLabel[_badge]] = True
            self.badge_submenu.append(
                MenuItem(self.raidLabel[_badge], self.toggleBadge, checked=lambda item: self.select_badges[str(item)])
            )
        # サブメニューに源世庫パニガルム追加
        self.genseiko = '源世庫パニガルム'
        self.select_badges[self.genseiko] = True
        self.badge_submenu.append(
            MenuItem(self.genseiko, self.toggleBadge, checked=lambda item: self.select_badges[str(item)])
        )
        self.badges = Badges()
        self.badges.start()

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
            'pani': str(),
            'ikai': str(),
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

    def toggleBadges(self, _, __):
        self.show_badges = not self.show_badges
        self.badges.set_visible(self.show_badges)

    def toggleBadge(self, _, item):
        self.select_badges[str(item)] = not self.select_badges[str(item)]
        self.updateBadges()

    def updateBadges(self):
        # バッジの更新
        images = []
        # バトルコンテンツを追加
        for _badge in self.raids:
            if self.select_badges[self.raidLabel[_badge]]:
                badge = (self.xnames[_badge] if _badge in self.xnames else _badge) + ('_open' if self.raids[_badge] else '_close')
                images.append(self.badge_cache[badge])

        # 源世庫パニガルム
        def dimm(image):
            return ImageEnhance.Brightness(image).enhance(0.6).convert('L')

        if self.select_badges[self.genseiko]:
            _, key = self.panigarm
            lst = list(panigarms)
            ic0 = lst.index(key)                    # now
            ic1 = (ic0 + 1) % len(panigarms)        # next
            ic2 = (ic1 + 1) % len(panigarms)        # next next
            images.append([                         # list
                self.badge_cache[lst[ic0]],
                dimm(self.badge_cache[lst[ic1]]),
                dimm(self.badge_cache[lst[ic2]]),
            ])

        # 現在の襲撃兵団を追加
        if self.icon_url:
            target = self.getTarget(self.icon_url)
            images.append(self.badge_cache[target])

        self.badges.update(images)

    def toggleTitle(self, _, __):
        self.badges.toggle_title()

    def updateMenu(self):
        now = self.getNow('%H:00')
        item = [
            MenuItem('Open', self.doOpen, default=True, visible=False),

            MenuItem('Show Badges', self.toggleBadges, checked=lambda _: self.show_badges),
            MenuItem('Select Badges', Menu(*self.badge_submenu)),
            MenuItem('Toggle Badges Title Bar', self.toggleTitle),
            Menu.SEPARATOR,

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
            item.append(MenuItem(f'{t} {titles[target]}', lambda _: False, enabled=target in NOTIFICATION_TARGET, checked=lambda x: str(x).split()[0] == now))
            idx += 1
            if idx >= MAX_MENUS:
                break
        item.append(Menu.SEPARATOR)

        # 天獄・インフェルノ・昏冥庫・異界の創造主
        # yyyy/mm/dd hh:59 まで {target}
        for key in self.raids:
            if self.raids[key]:
                url = f'{tengoku_url}#_{key}'
                item.append(MenuItem(f'{self.raids[key]}', lambda _: webbrowser.open(url), checked=lambda _: True))
        if any(self.raids.values()):
            item.append(Menu.SEPARATOR)

        # panigarm
        sdate, key = self.panigarm
        lst = list(panigarms)
        idx = lst.index(key)
        nxt = (idx + 1) % len(panigarms)
        nnxt = (idx + 2) % len(panigarms)
        espan = (sdate + td(days=NEXT_PANIGARM, hours=5, minutes=59)).strftime('%Y/%m/%d %H:%M まで')
        nspan = (sdate + td(days=NEXT_PANIGARM, hours=6)).strftime('%Y/%m/%d %H:%M から')
        nnspan = (sdate + td(days=NEXT_PANIGARM * 2, hours=6)).strftime('%Y/%m/%d %H:%M から')
        item.append(MenuItem(f'{espan} {panigarms.get(key, key)}', lambda _: False, checked=lambda _: True))
        item.append(MenuItem(f'{nspan} {panigarms[lst[nxt]]}', lambda _: False, checked=lambda _: False))
        item.append(MenuItem(f'{nnspan} {panigarms[lst[nnxt]]}', lambda _: False, checked=lambda _: False))

        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Exit', self.stopApp))
        return Menu(*item)

    def makeIconCache(self):
        def _makeIconImage(icon_url):
            with requests.get(icon_url) as r:
                image = Image.open(io.BytesIO(r.content))
                target = self.getTarget(icon_url)
                # store make badge excludes metal rookies
                if target != '1' and target not in self.badge_cache:
                    self.badge_cache[target] = image
                w, h = image.size
                # crop center
                icon_image = image.crop(((w - h) // 2, 0, (w + h) // 2, h)).resize((16, 16))
                # add gold frame
                if target in NOTIFICATION_TARGET:
                    draw = ImageDraw.Draw(icon_image)
                    draw.rectangle((0, 0, 15, 15), outline=GOLD, width=2)
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
        if self.enableMetal and self.nowMetal:
            # 1秒毎に返すアイコンが異なる感じ
            second = int(self.getNow('%S'))
            return icons[second % 2]

        return icons[0]

    def updateIcon(self, update_menu=True):
        target = self.getTarget(self.icon_url)
        icon_adf = self.icon_cache[target]
        icon_metal = self.icon_cache['1']
        self.app.icon = self.getIcon([icon_adf, icon_metal])
        if update_menu and self.enableMetal and self.nowMetal:
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
                panigarm = soup.find(class_='tokoyami-panigarm')
                icon_url = panigarm.find('img').get('src')
                key = self.getTarget(icon_url)
                start = re.sub(r'（.）', '', panigarm.find_all('th')[1].text.strip())
                yyyy = dt.now(tz(td(hours=+9), 'JST')).year
                mm, dd = re.findall(NUMS_RE, start)
                sdate = dt(year=yyyy, month=int(mm), day=int(dd))
                self.panigarm = [sdate, key]

                # store panigarms badge
                def _storePanigarmBadge(icon_url):
                    target = self.getTarget(icon_url)
                    if target not in self.badge_cache:
                        with requests.get(icon_url) as r:
                            image = Image.open(io.BytesIO(r.content)).resize((27, 27))
                            self.badge_cache[target] = image

                pani_url_fmt = icon_url.replace(key, '{}')
                for _key in panigarms:
                    if _key not in self.badge_cache:
                        pani_img_url = pani_url_fmt.format(_key)
                        _storePanigarmBadge(pani_img_url)

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

            # badge debug start

            # これやめてテキストから画像にするかも
            # 天獄
            # フェスタ
            # 昏冥庫
            # 異界
            # でセンタリング

            # closed の場合
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/tengoku.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/konmeiko.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/ikai_close.png?29439811
            # is-open の場合
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/tengoku_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/konmeiko_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/ikai_open.png?29439811
            def _makeBadgeImage(badge_url):
                with requests.get(badge_url) as r:
                    image = Image.open(io.BytesIO(r.content))
                    w, h = image.size
                    # crop upper area and border
                    x_offset = 8
                    y_offset = 6
                    badge_image = image.crop((0 + x_offset, 0 + y_offset, w - x_offset, (h // 2) - y_offset))
                    return badge_image

            urls = [img['src'] for img in soup.select('div.right-menu__battle a img')]
            for url in urls:
                target = self.getTarget(url)
                # _open, _close に正規化
                if '_' not in target and '_close' not in target:
                    target += '_close'
                if target not in self.badge_cache:
                    self.badge_cache[target] = _makeBadgeImage(url)
            # badge debug end

            # 天獄
            tengoku = soup.find(class_='tengoku is-open mt15')
            if tengoku:
                _span = tengoku.find(class_='tengoku__period').text.strip().split('\n')[-1].strip()
                yyyy, mm, dd, HH, MM = re.findall(NUMS_RE, _span)
                span = f'{yyyy}/{int(mm):02d}/{dd} {HH}:{MM} まで'
                target = soup.find(class_='tengoku-x-table_title').text.strip()
                print(self.getNow(), span, target)
                self.raids['tengoku'] = f'{span} {target}'

            # インフェルノ・昏冥庫・異界の創造主 (一部分共通化)
            for key in list(self.raids)[1:]:
                class_ = key
                if key in self.xclass:
                    class_ = self.xclass[key]
                opened = soup.find(class_=f'{class_} mt20 is-open')
                if opened:
                    span = opened.find(class_=f'{class_}-period').text.strip().split('\n')[-1].strip()
                    target = opened.find(class_=f'{class_}-target-label')
                    if key == 'ikai' and target is None:
                        target = '異界の創造主'
                    else:
                        target = target.text.strip()
                    print(self.getNow(), span, target)
                    self.raids[key] = f'{span} {target}'

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
            print(self.getNow(), titles[target])

            if target in NOTIFICATION_TARGET:
                Dracky(f'{now} {titles[target]}')

        self.updateBadges()

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
                    self.nowMetal = True
                    return
            self.nowMetal = False

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

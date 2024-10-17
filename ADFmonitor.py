# -*- coding: utf-8 -*-
import os
import sys
import io
import time
import threading
from datetime import datetime as dt, timedelta as td, timezone as tz
import webbrowser

import schedule
from pystray import Icon, Menu, MenuItem
from PIL import Image
import requests
from bs4 import BeautifulSoup
from win11toast import notify

TITLE = 'Astoltia Defense Force'
base_url = 'https://hiroba.dqx.jp/sc/tokoyami/#raid-container'
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
    "16": "鋼塊の重滅兵団",     # 仮
    "19": "全兵団",
}


class taskTray:
    def __init__(self):
        self.running = False
        self.icon_url = str()
        self.page_cache = {}

        self.updatePage()
        menu = self.updateMenu()
        self.app = Icon(name='PYTHON.win32.AstoltiaDefenseForce', title=TITLE, menu=menu)
        self.doCheck()

    def getNow(self):
        return dt.now(tz(td(hours=+9), 'JST')).strftime('%H:00')

    def getTarget(self, image_url):
        return image_url.split('/')[-1].split('.')[0]

    def doOpen(self):
        webbrowser.open(base_url)

    def updateMenu(self):
        now = self.getNow()
        item = [
            MenuItem('Open', self.doOpen, default=True, visible=False),
        ]

        matched = False
        for t in self.page_cache:
            # 現在以前はスキップ
            if t == now:
                matched = True
            if not matched:
                continue

            target = self.getTarget(self.page_cache[t])
            item.append(MenuItem(f'{t} {titles[target]}', lambda _: False, checked=lambda x: str(x).split()[0] == now))
        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Exit', self.stopApp))
        return Menu(*item)

    def updatePage(self):
        """
        毎日 6:00 に更新
        """
        with requests.get(base_url, timeout=10) as r:
            soup = BeautifulSoup(r.content, 'html.parser')
            # 同じクラスでメタルーキーもあるので先頭だけ
            tables = soup.find_all('table', class_='tokoyami-raid')[0]
            trs = tables.find_all('tr')

            for tr in trs:
                tds = tr.find_all('td')
                # th のときは td がないのでスキップ
                if len(tds) == 0:
                    continue

                hh, _ = tds[0].contents[0].strip().split('\xa0')[0].split(':')
                _time = f'{int(hh):02}:00'
                icon_url = tds[1].contents[1].get('src')
                self.page_cache[_time] = icon_url

        print(base_url, 'updated')

    def doCheck(self):
        """
        毎正時に更新
        """
        time.sleep(1)

        now = self.getNow()
        icon_url = self.page_cache[now]
        if icon_url != self.icon_url:
            self.icon_url = icon_url
            with requests.get(icon_url) as r:
                image = Image.open(io.BytesIO(r.content))
                w, h = image.size
                # crop center
                icon = image.crop(((w - h) // 2, 0, (w + h) // 2, h)).resize((16, 16))

                target = self.getTarget(icon_url)
                self.app.title = titles[target]
                self.app.menu = self.updateMenu()
                self.app.icon = icon
                self.app.update_menu()
                print(now, titles[target], 'icon updated')

                if target == '19':
                    def resource_path(path):
                        if hasattr(sys, '_MEIPASS'):
                            return os.path.join(sys._MEIPASS, path)
                        return os.path.join(os.path.abspath('.'), path)

                    notify(titles[target], app_id=TITLE, audio=resource_path('Assets/nc308516.mp3'))

    def runSchedule(self):
        schedule.every().day.at('06:00').do(self.updatePage)
        schedule.every().hour.at(':00').do(self.doCheck)

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

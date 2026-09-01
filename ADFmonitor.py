# -*- coding: utf-8 -*-
from dataclasses import asdict, dataclass
from datetime import datetime as dt, timedelta as td, timezone as tz
import ctypes
import hashlib
import io
import os
import re
import shutil
import sys
import threading
import time
import webbrowser
import winsound as ws

from PIL import Image, ImageEnhance
from bs4 import BeautifulSoup
from pystray import Icon, Menu, MenuItem
from tenacity import retry, stop_after_attempt, wait_fixed
from win11toast import notify
from winrt.windows.ui.notifications import ToastNotificationManager
from winrt.windows.ui.viewmanagement import UISettings
import darkdetect as dd
from requests import Session
import schedule

from Badges import Badges
from config import Config
from css import CSS
from utils import resource_path


class DQXSession(Session):
    def get(self, url, *args, **kwargs):
        from datetime import datetime
        print(f"{datetime.now().strftime('%H:%M:%S')} fetch {url}")
        return super().get(url, *args, **kwargs)


requests = DQXSession()

TITLE = 'Astoltia Defense Force'
WORK_DIR = os.path.join(os.environ.get('TEMP'), 'ADF')
if os.path.exists(WORK_DIR):
    shutil.rmtree(WORK_DIR)
os.makedirs(WORK_DIR)
tokoyami_url = 'https://hiroba.dqx.jp/sc/tokoyami/#raid-container'
tengoku_url = 'https://hiroba.dqx.jp/sc/game/tengoku'
tengoku_css = 'https://cache.hiroba.dqx.jp/dq_resource/css/game/tengoku.css'
MAX_MENUS = 7
# 翌日の先頭の準備
NEXT_DAY_MARK = 'NEXT_MARK'
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
    "19": "冥黒の悪夢兵団",
    "20": "全兵団",
}
# 紫炎の鉄機兵団, 冥黒の悪夢兵団, 全兵団
NOTIFICATION_TARGET = ['3', '19', '20']
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

XML_TEMPLATE = """
<toast activationType="protocol" launch="http:" scenario="{scenario}">
    <visual>
       <binding template='ToastGeneric'>
           <text placement="attribution">%attribution%</text>
       </binding>
    </visual>
</toast>
"""


def Dracky(message, icon={}, image={}, hero=False, label=None, on_click=None, work_dir=WORK_DIR):
    """
    message: text 空白に応じて title, body をセット
    icon: アイコン画像
    image: イメージ画像
    hero: image placement: True: 'hero'
    label: イベントの種類
    on_click: 通知をクリックしたときのリンク先

    邪神の宮殿・天獄
    フェスタ・インフェルノ
    昏冥庫パニガルム
    異界の創造主
    まもの博士の冒険的な実験
    源世庫パニガルム
    アストルティア防衛軍
    """
    # Notification Specification
    # https://learn.microsoft.com/en-us/uwp/api/windows.ui.notifications.toastnotification.tag?view=winrt-26100
    # group max length: 64
    # tag max length: 64
    # 25 + 1 + 32 = 58 < 64
    def _make_hash(name: str) -> str:
        return name[:25] + '_' + hashlib.md5(name.encode('utf-8')).hexdigest()

    def _label2hero(label_img: Image) -> Image:
        """
        label の 136x48 を hero の 364x180 に
        364x128 に拡大して縦にセンタリング(背景透明)
        """
        LW, LH = label_img.size
        HW, HH = (364, 180)

        # no scaling code
        # nh = int(HW / (LW / LH))
        # resized_img = label_img.resize((HW, nh), Image.Resampling.LANCZOS)

        try:
            current_factor = UISettings().text_scale_factor
        except Exception:
            current_factor = 1
        delta_m = 80.0 * (current_factor - 1.0)
        w_safe = max(200, HW - delta_m)
        ratio = w_safe / HW
        nw = int(ratio * HW)
        nh = int(ratio * HW / (LW / LH))
        resized_img = label_img.resize((nw, nh), Image.Resampling.LANCZOS)
        hero_img = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))
        hero_img.paste(resized_img, (0, int((HH - nh) / 2)))
        return hero_img

    def _make_img_cache(img: dict) -> str:
        name = list(img)[0]
        tmp_name = os.path.join(work_dir, name)
        if not os.path.exists(tmp_name):
            if name.startswith('label'):
                _image = _label2hero(img[name])
            else:
                _image = img[name]
            _image.save(tmp_name, format='PNG')
        return tmp_name

    # デフォルトイベントは防衛軍
    event = label if label else 'アストルティア防衛軍'

    group = _make_hash(TITLE)
    tag = _make_hash(event)

    # clear history with tag, group, app_id
    # avoid win11toast.clear_toast: in 0.36.3
    ToastNotificationManager.history.remove_grouped_tag_with_id(tag, group, TITLE)

    # delete notification only
    if not message:
        return

    # image spec: https://learn.microsoft.com/en-us/uwp/schemas/tiles/toastschema/element-image
    # アプリの権限として信頼されてないと file:/// 以外は は取れない
    # icon, image format
    # {
    #     str: PIL.Image
    # }
    if not icon:
        _icon = {
            'src': resource_path('Assets/sample.ico'),
            'placement': 'appLogoOverride',
        }
    else:
        _icon = {
            'src': _make_img_cache(icon),
            'placement': 'appLogoOverride',
        }

    _image = {}
    if image:
        _image['src'] = _make_img_cache(image)
        if hero:
            _image['placement'] = 'hero'

    lines = message.split(' ')
    title = lines[-1]
    body = ' '.join(lines[:-1])

    xml = XML_TEMPLATE.replace('%attribution%', event)
    notify(
        title,
        body=body,
        icon=_icon,
        image=_image,
        xml=xml,
        app_id=TITLE,
        group=group,
        tag=tag,
        on_click=on_click,
        audio={'silent': 'true'},
    )
    ws.PlaySound(resource_path('Assets/nc308516m.wav'), ws.SND_FILENAME)


def getVersion():
    v = 'test'
    try:
        with open(resource_path('Assets/version.txt')) as fd:
            v = fd.read().strip().removeprefix('v')
    except Exception:
        pass
    return f'{TITLE} {v}'


# 保存する設定の型定義
@dataclass
class Setting:
    # 兵団選択状態
    select_corps: dict[str, bool]
    # badgeの表示状態
    show_badges: bool
    # badgeの auto show hide
    auto_show_hide: bool
    # badgeの select状態 / 通知するイベントも兼ねる
    select_badges: dict[str, bool]
    # badgeの位置
    geometry: str
    # badgeのorientation
    orientation: str
    # badgeの fit mode
    is_fit_mode: bool
    # badgeの title bar 表示
    hide_title_bar: bool


class taskTray:
    def __init__(self):
        self.running = False
        self.config = Config(TITLE)
        self.icon_url = str()
        self.page_cache = {}
        self.tooltips = []
        self.metal_cache = []
        self.icon_cache = {}            # { "num": Image }
        self.badge_cache = {}
        self.enableMetal = False
        self.nowMetal = False
        self.raids = self.initRaids()
        self.on_clicks = self.initRaids()
        self.xclass = {
            'inferno': 'f-inferno',
            'pani': 'konmeiko',
        }
        self.xnames = {
            'pani': 'konmeiko',
        }
        self.xleaves = {
            'jikken': 'mamo',
        }
        self.panigarm = []              # [start datetime, hashkey]

        # 通知する兵団の初期化
        self.select_corps = {}
        self.corps_submenu = [
            MenuItem('Set All', self.setAll),
            MenuItem('Unset All', self.unsetAll),
            Menu.SEPARATOR,
        ]
        for _title in titles:
            title = titles[_title]
            self.select_corps[title] = _title in NOTIFICATION_TARGET
            self.corps_submenu.append(
                MenuItem(title, self.toggleCorps, checked=lambda item: self.select_corps[str(item)])
            )

        # バッジ周り初期化
        self.show_badges = False
        self.geometry = ''
        self.auto_show_hide = False
        self.raidLabel = {
            'tengoku': '邪神の宮殿 天獄',
            'inferno': 'フェスタ・インフェルノ',
            'pani': '昏冥庫パニガルム',
            'ikai': '異界の創造主',
            'jikken': '冒険的な実験',
        }
        self.last_events = self.raidLabel.copy()
        self.select_badges = {}
        # サブメニュー登録
        self.badge_submenu = [
            MenuItem('Auto Show / Hide Badges', self.toggleAutoShowHide, checked=lambda _: self.auto_show_hide),
            Menu.SEPARATOR,
        ]
        for _badge in self.raids:
            self.select_badges[self.raidLabel[_badge]] = False
            self.badge_submenu.append(
                MenuItem(self.raidLabel[_badge], self.toggleBadge, checked=lambda item: self.select_badges[str(item)])
            )
        # サブメニューに源世庫パニガルム追加
        self.genseiko = '源世庫パニガルム'
        self.select_badges[self.genseiko] = False
        self.last_events[self.genseiko] = self.genseiko
        self.badge_submenu.append(
            MenuItem(self.genseiko, self.toggleBadge, checked=lambda item: self.select_badges[str(item)])
        )
        self.badges = Badges()
        # コールバックを定義
        self.badges.on_changed = self.save_config
        self.badges.start()
        # 待機
        while not self.badges._ready:
            time.sleep(0.1)
        # 設定読み込み
        self.load_config()

        # 読み込み中フラグ解除
        self.badges.is_loading = False
        if hasattr(self, 'geometry'):
            self.badges.root.geometry(self.geometry)
        self.badges.set_visible(self.show_badges)

        self.updatePage(retry=False)
        if not self.page_cache:
            notify(body='メンテナンス中', app_id=TITLE, tag=TITLE, group=TITLE, duration='long')
            sys.exit(1)

        menu = self.updateMenu()
        self.app = Icon(name='PYTHON.win32.AstoltiaDefenseForce', title=TITLE, menu=menu)
        self.checkMetal()
        self.doCheck(wait=False)

    def load_config(self):
        try:
            setting = Setting(**self.config.load())
            self.show_badges = setting.show_badges
            self.auto_show_hide = setting.auto_show_hide
            # 今後レイドコンテンツが増えた時のためにガード
            for label in setting.select_badges:
                self.select_badges[label] = setting.select_badges[label]
            for key in self.raidLabel:
                label = self.raidLabel[key]
                if label not in self.select_badges:
                    self.select_badges[label] = False
            # 補正のために自分に保存(Badgesでは補正したときに反映される)
            self.geometry = setting.geometry
            self.badges.orientation = setting.orientation
            self.badges.is_fit_mode = setting.is_fit_mode
            self.badges.hide_title_bar = setting.hide_title_bar
            self.select_corps = setting.select_corps
        except Exception:
            pass

    def save_config(self):
        x = self.badges.root.winfo_x()
        y = self.badges.root.winfo_y()
        geometry = f'+{x}+{y}'

        setting = Setting(
            select_corps=self.select_corps,
            show_badges=self.show_badges,
            auto_show_hide=self.auto_show_hide,
            select_badges=self.select_badges,
            geometry=geometry,
            orientation=self.badges.orientation,
            is_fit_mode=self.badges.is_fit_mode,
            hide_title_bar=self.badges.hide_title_bar,
        )
        self.config.save(asdict(setting))
        self.updateMenu()
        self.app.title = '\n'.join(self.tooltips)

    def initRaids(self):
        return {
            'tengoku': str(),
            'inferno': str(),
            'pani': str(),
            'ikai': str(),
            'jikken': str(),
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

    def notifyCorps(self):
        now = self.getNow('%H:00')

        # icon, image 設定
        target = self.getTarget(self.page_cache[now])
        # image 用ラベル
        label = f'label{target}'
        icon = {target: self.icon_cache[target]}
        image = {}

        if label in self.badge_cache:
            image[label] = self.badge_cache[label]

        Dracky(
            f'{now} {titles[target]}',
            icon=icon,
            image=image,
            hero=True,
        )

    def setAll(self):
        for i in self.select_corps:
            self.select_corps[i] = True
        self.save_config()
        self.notifyCorps()

    def unsetAll(self):
        for i in self.select_corps:
            self.select_corps[i] = False
        self.save_config()

    def toggleCorps(self, _, item):
        item = str(item)
        self.select_corps[item] = not self.select_corps[item]
        self.save_config()
        # 現在の兵団かどうかチェック
        # 通知有効・襲撃中なら通知する
        now = self.getNow('%H:00')
        line = f'{now} {item}'
        if line in self.tooltips and self.select_corps[item]:
            self.notifyCorps()

    def toggleBadges(self, _, __):
        self.show_badges = not self.show_badges
        self.badges.set_visible(self.show_badges)
        self.save_config()

    def toggleBadge(self, _, item):
        self.select_badges[str(item)] = not self.select_badges[str(item)]
        self.updateBadges()
        self.save_config()

    def toggleAutoShowHide(self, _, __):
        self.auto_show_hide = not self.auto_show_hide
        self.updateBadges()
        self.save_config()

    def updateBadges(self):
        def small(img):
            return img.resize((27, 27))

        def dimm(image):
            return ImageEnhance.Brightness(image).enhance(0.5)

        # バッジの更新
        images = []
        # バトルコンテンツを追加
        for _badge in self.raids:
            if self.select_badges[self.raidLabel[_badge]]:
                badge = (self.xnames[_badge] if _badge in self.xnames else _badge) + ('_open' if self.raids[_badge] else '_close')
                if badge not in self.badge_cache:
                    t = badge.split('_')
                    if len(t) == 2:
                        badge = f'{t[0]}_fever_{t[1]}'
                if (not self.auto_show_hide) or (self.auto_show_hide and '_open' in badge):
                    images.append(self.badge_cache[badge])

        # 源世庫パニガルム
        if self.select_badges[self.genseiko]:
            _, key = self.panigarm
            lst = list(panigarms)
            ic0 = lst.index(key)                    # now
            ic1 = (ic0 + 1) % len(panigarms)        # next
            ic2 = (ic1 + 1) % len(panigarms)        # next next
            images.append([                         # list
                small(self.badge_cache[lst[ic0]]),
                small(dimm(self.badge_cache[lst[ic1]])),
                small(dimm(self.badge_cache[lst[ic2]])),
            ])

        adfs = []
        # 現在の襲撃兵団を追加
        if self.icon_url:
            target = self.getTarget(self.icon_url)
            adfs.append(self.badge_cache[target])
        # 次の襲撃兵団を追加
        now = self.getNow('%H')
        if now == '05':
            nxt = NEXT_DAY_MARK
        else:
            nxt = f'{(int(now) + 1) % 24:02}:00'
        nxt_img_url = self.page_cache[nxt]
        nxt_target = self.getTarget(nxt_img_url)
        nxt_img = self.badge_cache[nxt_target]
        adfs.append(dimm(nxt_img))

        images.append(adfs)

        self.badges.update(images)

    def toggleTitle(self, _, __):
        self.badges.toggle_title()

    def updateMenu(self):
        self.tooltips.clear()
        now = self.getNow('%H:00')
        item = [
            MenuItem('Open', self.doOpen, default=True, visible=False),

            MenuItem('Show Badges', self.toggleBadges, checked=lambda _: self.show_badges),
            MenuItem('Select Events', Menu(*self.badge_submenu)),
            MenuItem('Toggle Badges Title Bar', self.toggleTitle),
            Menu.SEPARATOR,
        ]

        # 天獄・インフェルノ・昏冥庫・異界の創造主・冒険的な実験
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

        # metal rookies menu
        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Check Metal Rookies', self.toggleMetal, checked=lambda _: self.enableMetal))
        item.append(Menu.SEPARATOR)

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
            if not matched or t == NEXT_DAY_MARK:
                continue

            target = self.getTarget(self.page_cache[t])
            title = titles[target]
            if self.select_corps[title]:
                # print(f'{t} {title}')
                self.tooltips.append(f'{t} {title}')
            item.append(
                MenuItem(
                    f'{t} {titles[target]}',
                    lambda _: False,
                    enabled=lambda x: self.select_corps[str(x).split()[1]],
                    checked=lambda x: str(x).split()[0] == now
                )
            )
            idx += 1
            if idx >= MAX_MENUS:
                break
        if idx < MAX_MENUS:
            # next day's first schedule
            target = self.getTarget(self.page_cache[NEXT_DAY_MARK])
            title = titles[target]
            if self.select_corps[title]:
                self.tooltips.append(f'06:00 {title}')
            item.append(
                MenuItem(
                    f'06:00 {titles[target]}',
                    lambda _: False,
                    enabled=lambda x: self.select_corps[str(x).split()[1]],
                )
            )

        if any(self.select_corps.values()):
            item.append(Menu.SEPARATOR)

        item.append(MenuItem('Select Corps', Menu(*self.corps_submenu)))
        item.append(Menu.SEPARATOR)
        item.append(MenuItem(f'Exit {getVersion()}', self.stopApp))

        # イベント発生チェック ---------------------------------------
        # 天獄・フェスタ・昏冥庫・異界・実験
        for key in self.raids:
            event = self.raids[key]
            label = self.raidLabel[key]
            laste = self.last_events[key]
            on_click = self.on_clicks[key]

            # DEBUG events test
            # if key == 'tengoku':
            #     event = '2026/06/11 05:59 まで 異形の獣たち'

            # selected and changed event
            if self.select_badges[label] and event != laste:
                xkey = f'{self.xnames[key] if key in self.xnames else key}'
                # print(f'>> {key=} {xkey=} {label=} {event=} {laste=}')
                image = {}
                if xkey in self.badge_cache:
                    image[xkey] = self.badge_cache[xkey]
                Dracky(event, image=image, hero=True, label=label, on_click=on_click)
                self.last_events[key] = event
                if event:
                    print(self.getNow(), event)

        # 源世庫パニガルム
        # 今のところ じげんりゅう 一択で通知(念のため配列に)
        label = self.genseiko
        # [start datetime, hashkey]
        _, icon_key = self.panigarm
        event = panigarms[icon_key]
        matched = event in ['じげんりゅう']
        # matched = True          # DEBUG: どの源世庫でもマッチ

        if self.select_badges[label] and matched and event != self.last_events[label]:
            icon = {
                icon_key: self.badge_cache[icon_key]
            }
            if event:
                title = f'{espan} {event}'
                print(self.getNow(), title)
            else:
                title = ''
            Dracky(title, image=icon, label=label)

        # 今回のイベントをセット
        self.last_events[label] = event
        # ------------------------------------------------------------

        return Menu(*item)

    def makeIconCache(self):
        def _makeIconImage(icon_url):
            with requests.get(icon_url) as r:
                image = Image.open(io.BytesIO(r.content))
                target = self.getTarget(icon_url)
                # store make badge excludes metal rookies
                w, h = image.size
                if target != '1' and target not in self.badge_cache:
                    # cut side 6 dot
                    self.badge_cache[target] = image.crop((6, 0, w - 6, h))
                # crop center
                icon_image = image.crop(((w - h) // 2, 0, (w + h) // 2, h))
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

    def updateIcon(self):
        target = self.getTarget(self.icon_url)
        icon_adf = self.icon_cache[target]
        icon_metal = self.icon_cache['1']
        self.app.icon = self.getIcon([icon_adf, icon_metal])

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

                # 翌日のキャッシュをクリア
                if NEXT_DAY_MARK in self.page_cache:
                    del self.page_cache[NEXT_DAY_MARK]
                for tr in trs:
                    tds = tr.find_all('td')
                    # th のときは td がないのでスキップ
                    if len(tds) == 0:
                        continue

                    if NEXT_DAY_MARK not in self.page_cache:
                        nxt_url = tds[2].contents[1].get('src')
                        self.page_cache[NEXT_DAY_MARK] = nxt_url

                    hh, _ = tds[0].contents[0].strip().split('\xa0')[0].split(':')
                    _time = f'{int(hh):02}:00'
                    icon_url = tds[1].contents[1].get('src')
                    self.page_cache[_time] = icon_url

                # metal rookies
                self.metal_cache.clear()
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

                # <ul class="raid-label mt20">
                uls = soup.find_all('ul', class_='raid-label')
                for ul in uls:
                    imgs = ul.find_all('img')
                    for img in imgs:
                        url = img.get('src')
                        if 'label' in url:
                            label = f'label{self.getTarget(url)}'
                            if label not in self.badge_cache:
                                with requests.get(url) as r:
                                    image = Image.open(io.BytesIO(r.content))
                                    self.badge_cache[label] = image

                # panigarm
                panigarm = soup.find_all(class_='tokoyami-panigarm')[1]
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
                            image = Image.open(io.BytesIO(r.content))
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

        # バトルコンテンツ出現情報CSS読みこみ
        self.css = CSS(tengoku_css)
        # バトルコンテンツ出現情報本体読み込み
        with requests.get(tengoku_url, timeout=10) as r:
            self.raids = self.initRaids()
            self.on_clicks = self.initRaids()
            soup = BeautifulSoup(r.content, 'html.parser')

            # バトルコンテンツ情報

            # closed の場合
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/tengoku.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno_fever_ycpxioJe8eXM7jYS5uyZ ?
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno_fever_close_ycpxioJe8eXM7jYS5uyZ ?
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/konmeiko.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/ikai_close.png?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/jikken_close.jpg?29705369
            # is-open の場合
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/tengoku_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/inferno_fever_open_ycpxioJe8eXM7jYS5uyZ
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/konmeiko_open.jpg?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/ikai_open.png?29439811
            # https://cache.hiroba.dqx.jp/dq_resource/img/common/right/navi/battle/jikken_open.jpg?29705369 ??
            #   天獄
            #   https://hiroba.dqx.jp/sc/game/tengoku#_tengoku
            #   https://cache.hiroba.dqx.jp/dq_resource/img/game/tengoku/open.jpg?201811152
            #   600x391
            #   フェスタ
            #   https://hiroba.dqx.jp/sc/game/tengoku#_inferno
            #   https://cache.hiroba.dqx.jp/dq_resource/img/game/inferno/open.png?456
            #   588x436
            #   昏冥庫
            #   https://hiroba.dqx.jp/sc/game/tengoku#_pani
            #   https://cache.hiroba.dqx.jp/dq_resource/img/game/konmeiko/open.png?456
            #   600x437
            #   異界の創造主
            #   https://hiroba.dqx.jp/sc/game/tengoku#_ikai
            #   https://cache.hiroba.dqx.jp/dq_resource/img/game/ikai/open.png?456
            #   600x437
            #   実験的な冒険
            #   https://hiroba.dqx.jp/sc/game/tengoku#_mamo
            #   https://cache.hiroba.dqx.jp/dq_resource/img/game/jikken/open.png?456
            #   600x430

            def _makeBadgeImage(badge_url):
                with requests.get(badge_url) as r:
                    image = Image.open(io.BytesIO(r.content))
                    w, h = image.size
                    # crop upper area and border
                    x_offset = 8
                    y_offset = 6
                    badge_image = image.crop((0 + x_offset, 0 + y_offset, w - x_offset, (h // 2) - y_offset))
                    return badge_image

            # badge debug start
            print('------ store: ------')
            urls = [img['src'] for img in soup.select('div.right-menu__battle a img')]
            for url in urls:
                target = self.getTarget(url)
                # _open, _close に正規化
                # print(f'0 {target=}')

                # どっちも取る
                for word in ['_open', '_close']:
                    if word in target:
                        i = target.index(word)
                        target = target[:i] + word
                # _open はすべてについていると仮定したコード
                if not target.endswith(('_open', '_close')):
                    target += '_close'

                # print(f'1 {target=}')
                if target not in self.badge_cache:
                    print(f'store {target}')
                    self.badge_cache[target] = _makeBadgeImage(url)

            print('------ keys: -------')
            for target in self.badge_cache:
                if '_' in target:
                    print(target)
            print('--------------------')
            # badge debug end

            def _makeHeroImage(image_url):
                # サイズが一定ではないので Hero 用に自力で調整
                # CSS から人力 computed
                try:
                    with requests.get(image_url) as r:
                        image = Image.open(io.BytesIO(r.content))
                        LW, LH = image.size

                        _class, _ext = image_url.split('/')[-2:]
                        xclass = self.xclass[_class] if _class in self.xclass else _class

                        offset = LH
                        if '.png' in _ext:
                            # # pngの謎クエリが描画範囲だった変態仕様
                            # query = image_url.split('?')[-1]
                            # offset = int(query)
                            # 自前で謎クエリを補完
                            offset = 456

                        sh = int(self.css.get_style(xclass, 'height').removesuffix('px'))
                        sp = int(self.css.get_style(xclass, 'padding-top').removesuffix('px'))

                        # 上が空きすぎでいるので sp で上をカットオフ
                        img = image.crop((0, (offset - sh) + sp, LW, LH))
                        # print(' cropped', img.size)

                        # アスペクト比を維持したまま Hero サイズに縮小
                        HW, HH = (364, 180)
                        OW, OH = img.size
                        rate = HW / OW
                        nh = int(OH * rate)
                        res_img = img.resize((HW, nh))
                        # print(' resized', res_img.size)

                        # だいたい nh > HH なので上下のよぶんなところをカット
                        # 焼き込まれている文字列はだいたい真ん中にいるので
                        crop_img = res_img.crop((0, (nh - HH) // 2, HW, (nh - HH) // 2 + HH))

                        return crop_img
                except Exception:
                    return None

            def _build_on_click_with_cache(key):
                name = f'{self.xnames[key] if key in self.xnames else key}'
                leaf = f'_{self.xleaves[key] if key in self.xleaves else key}'
                # 天獄時のみ jpg なので今は決め打ち
                ext = f'{"jpg" if key == "tengoku" else "png"}'

                on_click = f'{tengoku_url}#{leaf}'
                # CSS の相対パスを正規化するのが面倒だったので自前生成(そのため謎クエリがない)
                image_url = f'https://cache.hiroba.dqx.jp/dq_resource/img/game/{name}/open.{ext}'
                if name not in self.badge_cache:
                    image = _makeHeroImage(image_url)
                    if image:
                        print(f'store {name}')
                        self.badge_cache[name] = image
                return on_click

            # 天獄
            tengoku = soup.find(class_='tengoku is-open mt15')
            if tengoku:
                _span = tengoku.find(class_='tengoku__period').text.strip().split('\n')[-1].strip()
                yyyy, mm, dd, HH, MM = re.findall(NUMS_RE, _span)
                span = f'{yyyy}/{int(mm):02d}/{int(dd):02d} {HH}:{MM} まで'
                target = soup.find(class_='tengoku-x-table_title').text.strip()
                key = 'tengoku'
                self.raids[key] = f'{span} {target}'
                self.on_clicks[key] = _build_on_click_with_cache(key)

            # インフェルノ・昏冥庫・異界の創造主・冒険的な実験 (一部分共通化)
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
                    elif key == 'jikken' and target is None:
                        target = '特別なモンスター'
                    else:
                        target = target.text.strip()
                    self.raids[key] = f'{span} {target}'
                    self.on_clicks[key] = _build_on_click_with_cache(key)

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
            self.updateIcon()
            target = self.getTarget(self.icon_url)
            self.app.menu = self.updateMenu()

            # ------------------------------------------------------------
            # TODO: NEED CHECK LENGTH
            # self.tooltips built with self.updateMenu()
            # tooltip = ''
            # for line in self.tooltips:
            #     # wchar 128 => 256
            #     if len(bytes(tooltip + '\n' + line, 'utf-8')) > 256 - 1:
            #         break
            #     if tooltip:
            #         tooltip += '\n'
            #     tooltip += line
            # l_plus = len(bytes(tooltip, 'utf-8'))
            # print('tooltip +=   len max 256', l_plus)
            # l_join = len(bytes('\n'.join(self.tooltips), 'utf-8'))
            # print('tooltip join len max 256', l_join)
            # self.app.title = tooltip
            self.app.title = '\n'.join(self.tooltips)
            # ------------------------------------------------------------

            self.app.update_menu()
            print(self.getNow(), titles[target])

            # 兵団の通知
            if self.select_corps[titles[target]]:
                self.notifyCorps()
            else:
                Dracky('')

        self.updateBadges()

    def checkMetal(self):
        """
        :00, :30 にチェック
        """
        self.app.menu = self.updateMenu()
        self.app.update_menu()
        if self.enableMetal:
            label = '大行進予報'
            icon_key = '1'
            icon = {
                icon_key: self.icon_cache[icon_key]
            }
            for t in self.metal_cache:
                if self.isMetal(t):
                    Dracky(f'{t} メタルーキー軍団大行進中', icon=icon, label=label)
                    self.nowMetal = True
                    return
            self.nowMetal = False
            Dracky('', label=label)

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

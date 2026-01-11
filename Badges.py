# -*- coding: utf-8 -*-
import threading
import tkinter as tk
from PIL import ImageTk


class Badges(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.root = None
        self.container = None
        self.photo_refs = []
        self._ready = False
        self.trans_color = '#abcdef'
        self.offset_x = 0
        self.offset_y = 0
        self.orientation = 'horizontal'
        self.current_images = []

    def run(self):
        self.root = tk.Tk()
        self.root.title('Badge')

        # 背景と透過
        self.root.config(bg=self.trans_color)
        self.root.wm_attributes('-transparentcolor', self.trans_color)

        # 枠なし・最前面・タスクバーアイコン非表示
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-toolwindow', True)

        # マウスイベント
        self.root.bind('<Button-1>', self.start_drag)
        self.root.bind('<B1-Motion>', self.drag_window)

        self.root.withdraw()

        self.container = tk.Frame(self.root, bg=self.trans_color)
        self.container.pack(padx=0, pady=0)

        # ★【最終手段】最前面を維持し続けるループを開始
        self._keep_on_top_loop()

        self._ready = True
        self.root.mainloop()

    def toggle_orientation(self):
        orientation = 'vertical' if self.orientation == 'horizontal' else 'horizontal'
        self.update(self.current_images, orientation=orientation)

    def update(self, pil_images, orientation=None):
        """表示状態にかかわらず、containerの中身を最新にする"""
        if not self._ready:
            return

        if pil_images is not None:
            self.current_images = pil_images

        # 指定があれば更新、なければ現在の状態を維持
        if orientation:
            self.orientation = orientation

        def _do_update():
            # 既存のウィジェットを掃除
            for widget in self.container.winfo_children():
                widget.destroy()
            self.photo_refs.clear()

            side_option = tk.LEFT if self.orientation == 'horizontal' else tk.TOP

            # 新しい画像を配置
            for img_obj in self.current_images:
                tk_img = ImageTk.PhotoImage(img_obj)
                self.photo_refs.append(tk_img)
                label = tk.Label(self.container, image=tk_img, bg=self.trans_color)

                # イベントバインド
                label.bind('<Button-1>', self.start_drag)
                label.bind('<B1-Motion>', self.drag_window)
                label.bind('<Button-3>', lambda e: self.toggle_orientation())
                label.pack(side=side_option, padx=0, pady=0)

            # コンテナサイズを再計算
            self.root.geometry('')
            self.root.update_idletasks()
            self.root.after(100, self._clamp_position)

            # 表示中なら最前面を再適用
            if self.root.state() == 'normal':
                self._force_topmost()

        # スレッドセーフに実行
        self.root.after(0, _do_update)

    def _clamp_position(self):
        """現在の位置が画面外なら中に戻す処理（ドラッグ中以外でも有用）"""
        x, y = self.root.winfo_x(), self.root.winfo_y()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        ww, wh = self.root.winfo_width(), self.root.winfo_height()
        nx = max(0, min(x, sw - ww))
        ny = max(0, min(y, sh - wh))
        self.root.geometry(f"+{nx}+{ny}")

    # --- 2. 表示状態だけを切り替えるメソッド ---
    def set_visible(self, visible: bool):
        """ウィンドウの表示・非表示だけを制御する"""
        if not self._ready:
            return

        def _do_toggle():
            if visible:
                self.root.deiconify()
                self._force_topmost()
            else:
                self.root.withdraw()

        self.root.after(0, _do_toggle)

    def _keep_on_top_loop(self):
        """ウィンドウが表示されている間、0.1秒ごとに最前面を強制する"""
        if self.root:
            # ウィンドウが表示状態(normal)の時だけ実行
            if self.root.state() == 'normal':
                # lift() と topmost 再設定の合わせ技
                self.root.lift()
                self.root.attributes('-topmost', True)

            # 100ms後に自分を再帰的に呼び出す
            self.root.after(100, self._keep_on_top_loop)

    def _force_topmost(self):
        """即座に最前面へ引き上げる（クリック時用）"""
        if self.root:
            self.root.attributes('-topmost', False)
            self.root.attributes('-topmost', True)
            self.root.lift()

    def start_drag(self, event):
        self.offset_x = event.x
        self.offset_y = event.y
        self._force_topmost()

    def drag_window(self, event):
        if self.root:
            # 1. マウスの動きから計算上の新しい位置を出す
            new_x = self.root.winfo_x() + (event.x - self.offset_x)
            new_y = self.root.winfo_y() + (event.y - self.offset_y)

            # 2. 画面の幅と高さを取得
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()

            # 3. ウィンドウ自体の幅と高さを取得
            win_w = self.root.winfo_width()
            win_h = self.root.winfo_height()

            # 4. 座標を画面内に収める (クランプ処理)
            # 左端(0) と 右端(画面幅 - ウィンドウ幅) の間に収める
            new_x = max(0, min(new_x, screen_w - win_w))
            # 上端(0) と 下端(画面高 - ウィンドウ高) の間に収める
            new_y = max(0, min(new_y, screen_h - win_h))

            # 5. 制限された座標を適用
            self.root.geometry(f'+{new_x}+{new_y}')

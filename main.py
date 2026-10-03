import os
import sys
import sqlite3
import datetime
import threading
import random
import webbrowser

from kivy.utils import platform
IS_ANDROID = (platform == "android")

if IS_ANDROID:
    from jnius import autoclass
    AndroidMediaPlayer = autoclass("android.media.MediaPlayer")
else:
    AndroidMediaPlayer = None

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.graphics import Color, RoundedRectangle
from kivy.core.window import Window

import requests
import yt_dlp

# =========================================================
# TEMA VE RENK PALETLERİ
# =========================================================
THEMES = {
    "Mor Neon": {"accent": "#B026FF", "hover": "#8C00E6", "mode": "Dark", "card_bg": "#1A1423", "btn_bg": "#2B1E3D", "border": "#7B1FA2"},
    "Mavi Neon": {"accent": "#00D2FF", "hover": "#0099DD", "mode": "Dark", "card_bg": "#101D28", "btn_bg": "#172E40", "border": "#00838F"},
    "Kırmızı Neon": {"accent": "#FF2A6D", "hover": "#D11A53", "mode": "Dark", "card_bg": "#24131A", "btn_bg": "#3B1B26", "border": "#C2185B"},
    "Yeşil Neon": {"accent": "#00FF87", "hover": "#00C868", "mode": "Dark", "card_bg": "#10241A", "btn_bg": "#193D2A", "border": "#2E7D32"},
    "Karanlık": {"accent": "#7289DA", "hover": "#5B6EAE", "mode": "Dark", "card_bg": "#23272A", "btn_bg": "#2C2F33", "border": "#4E5D94"},
    "Aydınlık": {"accent": "#0066CC", "hover": "#004999", "mode": "Light", "card_bg": "#EAEAEA", "btn_bg": "#D0D0D0", "border": "#999999"}
}

# =========================================================
# VERİTABANI YÖNETİMİ
# =========================================================
class DatabaseManager:
    def __init__(self, db_name="emory.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS profile (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT DEFAULT 'Dinleyici',
                        theme TEXT DEFAULT 'Mor Neon',
                        accent_color TEXT DEFAULT '#B026FF'
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS play_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        artist TEXT,
                        genre TEXT,
                        duration_seconds INTEGER,
                        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        artist TEXT,
                        web_url TEXT,
                        thumbnail TEXT,
                        UNIQUE(title, artist)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        artist TEXT,
                        file_path TEXT,
                        thumbnail TEXT,
                        UNIQUE(title, artist)
                    )
                """)
                cursor.execute("SELECT COUNT(*) FROM profile")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO profile (username, theme, accent_color) VALUES ('Dinleyici', 'Mor Neon', '#B026FF')")
                conn.commit()
        except Exception as e:
            print(f"Veritabanı hatası: {e}")

    def get_profile(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, theme, accent_color FROM profile LIMIT 1")
            row = cursor.fetchone()
            if row:
                return (row[0] or "Dinleyici", row[1] if row[1] in THEMES else "Mor Neon", row[2] or "#B026FF")
            return ("Dinleyici", "Mor Neon", "#B026FF")

    def update_profile(self, username, theme, accent_color="#B026FF"):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE profile SET username = ?, theme = ?, accent_color = ? WHERE id = 1", (username, theme, accent_color))
            conn.commit()

    def add_play_log(self, title, artist, genre, duration_seconds):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO play_history (title, artist, genre, duration_seconds) VALUES (?, ?, ?, ?)",
                           (title, artist, genre, duration_seconds))
            conn.commit()

    def get_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - datetime.timedelta(days=7)
            month_start = today_start - datetime.timedelta(days=30)
            year_start = today_start - datetime.timedelta(days=365)

            def fetch_seconds(since_date):
                cursor.execute("SELECT SUM(duration_seconds) FROM play_history WHERE played_at >= ?", (since_date.strftime("%Y-%m-%d %H:%M:%S"),))
                res = cursor.fetchone()[0]
                return res if res else 0

            cursor.execute("SELECT artist, COUNT(*) as count FROM play_history GROUP BY artist ORDER BY count DESC LIMIT 5")
            top_artists = cursor.fetchall()
            cursor.execute("SELECT genre, COUNT(*) as count FROM play_history GROUP BY genre ORDER BY count DESC LIMIT 5")
            top_genres = cursor.fetchall()

            return {
                "daily": fetch_seconds(today_start),
                "weekly": fetch_seconds(week_start),
                "monthly": fetch_seconds(month_start),
                "yearly": fetch_seconds(year_start),
                "top_artists": top_artists,
                "top_genres": top_genres
            }

    def get_recent_tracks(self, limit=20):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, artist, genre FROM play_history ORDER BY id DESC LIMIT ?", (limit,))
            return cursor.fetchall()

    def add_favorite(self, title, artist, web_url, thumbnail):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO favorites (title, artist, web_url, thumbnail) VALUES (?, ?, ?, ?)",
                               (title, artist, web_url, thumbnail))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_favorite(self, title, artist):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM favorites WHERE title = ? AND artist = ?", (title, artist))
            conn.commit()
            return True

    def is_favorite(self, title, artist):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM favorites WHERE title = ? AND artist = ?", (title, artist))
            return cursor.fetchone() is not None

    def get_favorites(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, artist, web_url, thumbnail FROM favorites")
            return cursor.fetchall()

    def add_download(self, title, artist, file_path, thumbnail):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO downloads (title, artist, file_path, thumbnail) VALUES (?, ?, ?, ?)",
                               (title, artist, file_path, thumbnail))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_downloads(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, artist, file_path, thumbnail FROM downloads")
            return cursor.fetchall()

# =========================================================
# MÜZİK MOTORU
# =========================================================
class AudioBackend:
    """Android'de MediaPlayer, masaustunde (test icin) Kivy SoundLoader."""
    def __init__(self):
        self.mp = None
        self.sound = None

    def load_and_play(self, source):
        self.release()
        if IS_ANDROID:
            self.mp = AndroidMediaPlayer()
            self.mp.setDataSource(source)
            self.mp.prepare()
            self.mp.start()
        else:
            from kivy.core.audio import SoundLoader
            self.sound = SoundLoader.load(source)
            if self.sound:
                self.sound.play()

    def pause(self):
        if self.mp:
            self.mp.pause()
        elif self.sound:
            self._sound_pos = self.sound.get_pos()
            self.sound.stop()

    def resume(self):
        if self.mp:
            self.mp.start()
        elif self.sound:
            self.sound.play()
            if getattr(self, "_sound_pos", 0):
                self.sound.seek(self._sound_pos)

    def release(self):
        if self.mp:
            try:
                self.mp.stop()
                self.mp.release()
            except Exception:
                pass
            self.mp = None
        if self.sound:
            try:
                self.sound.stop()
                self.sound.unload()
            except Exception:
                pass
            self.sound = None

    def get_fraction(self):
        try:
            if self.mp:
                dur = self.mp.getDuration()
                return self.mp.getCurrentPosition() / dur if dur > 0 else 0.0
            if self.sound and self.sound.length:
                return self.sound.get_pos() / self.sound.length
        except Exception:
            pass
        return 0.0

    def seek_fraction(self, frac):
        try:
            if self.mp:
                dur = self.mp.getDuration()
                if dur > 0:
                    self.mp.seekTo(int(frac * dur))
            elif self.sound and self.sound.length:
                self.sound.seek(frac * self.sound.length)
        except Exception:
            pass

    def set_volume(self, percent):
        v = max(0.0, min(1.0, percent / 100.0))
        if self.mp:
            self.mp.setVolume(v, v)
        elif self.sound:
            self.sound.volume = v


class MusicEngine:
    def __init__(self, db: DatabaseManager, download_dir="downloads"):
        self.db = db
        self.audio = AudioBackend()
        self.is_playing = False
        self.current_song = None
        self.start_time = None
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    def search_online(self, query):
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True
        }
        musical_query = f"{query} song audio official" if not query.startswith("http") else query
        search_target = f"ytsearch10:{musical_query}" if not query.startswith("http") else query

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(search_target, download=False)
                results = []
                entries = info.get('entries', []) if info else []
                exclude_keywords = ['gameplay', 'oynanis', 'oynanış', 'walkthrough', 'trailer', 'fragman', 'reaction', 'tepki', 'review', 'tutorial']

                for entry in entries:
                    if not entry:
                        continue
                    title = entry.get('title', 'Bilinmeyen Şarkı')
                    if any(kw in title.lower() for kw in exclude_keywords):
                        continue

                    v_id = entry.get('id')
                    url = entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={v_id}"
                    thumbs = entry.get('thumbnails', [])
                    thumb_url = thumbs[-1].get('url', '') if thumbs else (f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg" if v_id else "")

                    results.append({
                        'title': title,
                        'artist': entry.get('uploader') or entry.get('channel') or 'Bilinmeyen Sanatçı',
                        'genre': 'Müzik',
                        'web_url': url,
                        'audio_url': None,
                        'thumbnail': thumb_url,
                        'is_offline': False
                    })
                    if len(results) >= 10:
                        break
                return results
            except Exception as e:
                print(f"Arama hatası: {e}")
                return []

    def play(self, song):
        try:
            if self.is_playing:
                self.stop_and_log()

            if song.get('is_offline') and os.path.exists(song.get('file_path', '')):
                source = song['file_path']
            else:
                source = song.get('audio_url')
                if not source and song.get('web_url'):
                    ydl_opts = {
                        'format': 'bestaudio[ext=m4a]/bestaudio/best',
                        'quiet': True,
                        'no_warnings': True,
                        'cachedir': False
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(song['web_url'], download=False)
                        source = info.get('url')
                        song['audio_url'] = source
            if not source:
                return

            self.audio.load_and_play(source)
            self.is_playing = True
            self.current_song = song
            self.start_time = datetime.datetime.now()
        except Exception as e:
            print(f"Oynatma hatası: {e}")

    def pause_resume(self):
        if not self.current_song:
            return
        if self.is_playing:
            self.audio.pause()
            self.is_playing = False
        else:
            self.audio.resume()
            self.is_playing = True

    def stop_and_log(self):
        if self.current_song and self.start_time:
            elapsed = (datetime.datetime.now() - self.start_time).seconds
            if elapsed > 3:
                self.db.add_play_log(
                    self.current_song['title'],
                    self.current_song['artist'],
                    self.current_song.get('genre', 'Genel'),
                    elapsed
                )
        self.audio.release()
        self.is_playing = False

    def set_volume(self, volume_percent):
        self.audio.set_volume(volume_percent)

    def get_position(self):
        return self.audio.get_fraction()

    def set_position(self, pos):
        self.audio.seek_fraction(pos)

    def download_song(self, song, callback=None):
        """Ses dosyasini m4a olarak indirir (Android'de FFmpeg olmadigi icin mp3 donusumu yok)."""
        def _download():
            try:
                clean_title = "".join(c for c in song['title'] if c.isalnum() or c in (' ', '_', '-')).strip() or "sarki"
                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(self.download_dir, f"{clean_title}.%(ext)s"),
                    'quiet': True,
                    'no_warnings': True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(song['web_url'], download=True)
                    output_path = ydl.prepare_filename(info)

                self.db.add_download(song['title'], song['artist'], output_path, song.get('thumbnail', ''))
                if callback:
                    callback(True, song['title'])
            except Exception as e:
                print(f"İndirme hatası: {e}")
                if callback:
                    callback(False, song['title'])
        threading.Thread(target=_download, daemon=True).start()

# =========================================================
# KIVY UI BİLEŞENLERİ VE EKRANLAR
# =========================================================
class EmoryApp(App):
    def build(self):
        if not IS_ANDROID:
            Window.size = (400, 780)
        self.db = DatabaseManager(os.path.join(self.user_data_dir, "emory.db"))
        self.engine = MusicEngine(self.db, os.path.join(self.user_data_dir, "downloads"))
        self.queue = []
        self.current_index = 0
        self.is_shuffle = False
        self.is_repeat = False
        self.is_programmatic_change = False

        user_info = self.db.get_profile()
        self.username = user_info[0]
        self.current_theme_name = user_info[1]

        theme_cfg = THEMES.get(self.current_theme_name, THEMES["Mor Neon"])
        self.accent_color = theme_cfg["accent"]
        self.hover_color = theme_cfg["hover"]
        self.card_bg = theme_cfg["card_bg"]
        self.btn_bg = theme_cfg["btn_bg"]
        self.border_color = theme_cfg["border"]

        root = BoxLayout(orientation='vertical')

        # Üst Navigasyon Çubuğu
        top_bar = BoxLayout(size_hint_y=None, height=50, padding=10, spacing=10)
        with top_bar.canvas.before:
            Color(rgba=get_color_from_hex("#100D1A"))
            self.top_bar_rect = RoundedRectangle(size=top_bar.size, pos=top_bar.pos, radius=[0, 0, 12, 12])
        top_bar.bind(size=lambda s, w: setattr(self.top_bar_rect, 'size', w),
                     pos=lambda s, p: setattr(self.top_bar_rect, 'pos', p))

        menu_btn = Button(text="[Menü]", size_hint_x=None, width=65, background_color=(0,0,0,0), color=get_color_from_hex(self.accent_color), font_size=13, bold=True)
        menu_btn.bind(on_press=self.open_nav_drawer)
        top_bar.add_widget(menu_btn)

        self.title_lbl = Label(text="EMORY MOBILE", bold=True, color=get_color_from_hex(self.accent_color), font_size=16)
        top_bar.add_widget(self.title_lbl)
        root.add_widget(top_bar)

        # Ekran Yöneticisi
        self.sm = ScreenManager(transition=SlideTransition())

        self.home_screen = Screen(name='home')
        self.setup_home_layout(self.home_screen)
        self.sm.add_widget(self.home_screen)

        self.offline_screen = Screen(name='offline')
        self.setup_offline_layout(self.offline_screen)
        self.sm.add_widget(self.offline_screen)

        self.favorites_screen = Screen(name='favorites')
        self.setup_favorites_layout(self.favorites_screen)
        self.sm.add_widget(self.favorites_screen)

        self.stats_screen = Screen(name='stats')
        self.setup_stats_layout(self.stats_screen)
        self.sm.add_widget(self.stats_screen)

        self.ai_screen = Screen(name='ai')
        self.setup_ai_layout(self.ai_screen)
        self.sm.add_widget(self.ai_screen)

        self.profile_screen = Screen(name='profile')
        self.setup_profile_layout(self.profile_screen)
        self.sm.add_widget(self.profile_screen)

        self.settings_screen = Screen(name='settings')
        self.setup_settings_layout(self.settings_screen)
        self.sm.add_widget(self.settings_screen)

        root.add_widget(self.sm)

        # Alt Oynatıcı Paneli (Player Bar)
        player_bar = BoxLayout(orientation='vertical', size_hint_y=None, height=170, padding=8, spacing=4)
        with player_bar.canvas.before:
            Color(rgba=get_color_from_hex("#0A0814"))
            self.player_rect = RoundedRectangle(size=player_bar.size, pos=player_bar.pos, radius=[16, 16, 0, 0])
        player_bar.bind(size=lambda s, w: setattr(self.player_rect, 'size', w),
                        pos=lambda s, p: setattr(self.player_rect, 'pos', p))

        info_row = BoxLayout(size_hint_y=None, height=32, spacing=10)
        self.lbl_now_title = Label(text="Şarkı Seçilmedi", bold=True, color=(1,1,1,1), font_size=13, halign='left')
        self.lbl_now_title.bind(size=lambda s, w: setattr(s, 'text_size', w))
        info_row.add_widget(self.lbl_now_title)

        self.btn_lyrics_mini = Button(text="Altyazı", size_hint_x=None, width=75, background_color=get_color_from_hex(self.accent_color), color=(1,1,1,1), font_size=11, bold=True)
        self.btn_lyrics_mini.bind(on_press=lambda x: self.open_lyrics_popup())
        info_row.add_widget(self.btn_lyrics_mini)
        player_bar.add_widget(info_row)

        self.progress_slider = Slider(min=0, max=1, value=0, size_hint_y=None, height=18)
        self.progress_slider.bind(value=self.on_slider_value_change)
        player_bar.add_widget(self.progress_slider)

        ctrl_row = BoxLayout(size_hint_y=None, height=42, spacing=6)

        self.btn_shuffle = Button(text="Karıştır", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=10, bold=True)
        self.btn_shuffle.bind(on_press=self.toggle_shuffle)
        ctrl_row.add_widget(self.btn_shuffle)

        btn_prev = Button(text="<<", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=12, bold=True)
        btn_prev.bind(on_press=lambda x: self.play_prev())
        ctrl_row.add_widget(btn_prev)

        self.btn_play = Button(text="Oynat", background_color=get_color_from_hex(self.accent_color), color=(1,1,1,1), bold=True, font_size=13)
        self.btn_play.bind(on_press=lambda x: self.toggle_play())
        ctrl_row.add_widget(self.btn_play)

        btn_next = Button(text=">>", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=12, bold=True)
        btn_next.bind(on_press=lambda x: self.play_next())
        ctrl_row.add_widget(btn_next)

        self.btn_repeat = Button(text="Tekrar", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=10, bold=True)
        self.btn_repeat.bind(on_press=self.toggle_repeat)
        ctrl_row.add_widget(self.btn_repeat)

        player_bar.add_widget(ctrl_row)

        special_ctrl_row = BoxLayout(size_hint_y=None, height=42, spacing=8)

        self.btn_like = Button(text="Beğenme", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=11, bold=True)
        self.btn_like.bind(on_press=self.toggle_favorite_action)
        special_ctrl_row.add_widget(self.btn_like)

        self.btn_mod_switch = Button(text="Mod Değiştirme", background_color=get_color_from_hex("#181324"), color=(1,1,1,1), font_size=11, bold=True)
        self.btn_mod_switch.bind(on_press=self.cycle_theme_mode)
        special_ctrl_row.add_widget(self.btn_mod_switch)

        player_bar.add_widget(special_ctrl_row)
        root.add_widget(player_bar)

        Clock.schedule_interval(self.update_loop, 0.8)
        return root

    def on_slider_value_change(self, instance, value):
        if self.is_programmatic_change:
            return
        self.engine.set_position(value)

    def cycle_theme_mode(self, instance):
        theme_names = list(THEMES.keys())
        try:
            current_idx = theme_names.index(self.current_theme_name)
            next_idx = (current_idx + 1) % len(theme_names)
        except ValueError:
            next_idx = 0
        new_theme = theme_names[next_idx]
        self.apply_theme(new_theme)

    def apply_theme(self, theme_name):
        self.current_theme_name = theme_name
        cfg = THEMES[theme_name]
        self.accent_color = cfg["accent"]
        self.hover_color = cfg["hover"]
        self.card_bg = cfg["card_bg"]
        self.btn_bg = cfg["btn_bg"]
        self.border_color = cfg["border"]
        self.db.update_profile(self.username, theme_name, self.accent_color)
        self.title_lbl.color = get_color_from_hex(self.accent_color)
        self.btn_play.background_color = get_color_from_hex(self.accent_color)
        self.btn_lyrics_mini.background_color = get_color_from_hex(self.accent_color)

    def toggle_favorite_action(self, instance):
        if not self.engine.current_song:
            return
        song = self.engine.current_song
        title = song['title']
        artist = song['artist']
        if self.db.is_favorite(title, artist):
            self.db.remove_favorite(title, artist)
            self.btn_like.background_color = get_color_from_hex("#181324")
        else:
            self.db.add_favorite(title, artist, song.get('web_url', ''), song.get('thumbnail', ''))
            self.btn_like.background_color = get_color_from_hex(self.accent_color)

    def update_like_button_state(self):
        if not self.engine.current_song:
            self.btn_like.background_color = get_color_from_hex("#181324")
            return
        song = self.engine.current_song
        if self.db.is_favorite(song['title'], song['artist']):
            self.btn_like.background_color = get_color_from_hex(self.accent_color)
        else:
            self.btn_like.background_color = get_color_from_hex("#181324")

    def open_nav_drawer(self, instance):
        content = BoxLayout(orientation='vertical', padding=10, spacing=8)
        with content.canvas.before:
            Color(rgba=get_color_from_hex("#100D1A"))
            crect = RoundedRectangle(size=content.size, pos=content.pos)
        content.bind(size=lambda s, w, r=crect: setattr(r, 'size', w),
                     pos=lambda s, p, r=crect: setattr(r, 'pos', p))

        nav_buttons = [
            ("Ana Sayfa & Keşfet", 'home'),
            ("Çevrim Dışı Kitaplık", 'offline'),
            ("Beğenilen Şarkılar", 'favorites'),
            ("Dinleme Analizi", 'stats'),
            ("AI Öneri Motoru", 'ai'),
            ("Profil Ayarları", 'profile'),
            ("Tema Seçenekleri", 'settings')
        ]

        popup = Popup(title="EMORY MENÜ", content=content, size_hint=(0.75, 0.85))

        for text, screen_name in nav_buttons:
            btn = Button(text=text, background_color=get_color_from_hex(self.btn_bg), color=(1,1,1,1), bold=True, size_hint_y=None, height=45)
            def change_screen(btn_instance, s=screen_name):
                self.sm.current = s
                popup.dismiss()
            btn.bind(on_press=change_screen)
            content.add_widget(btn)

        soc_lbl = Label(text="TOPLULUK", bold=True, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=25)
        content.add_widget(soc_lbl)

        btn_tg = Button(text="Telegram", background_color=get_color_from_hex("#0088CC"), color=(1,1,1,1), bold=True, size_hint_y=None, height=38)
        btn_tg.bind(on_press=lambda x: webbrowser.open("https://t.me/+GJVvm2tpZXY3ZWM0"))
        content.add_widget(btn_tg)

        btn_owner = Button(text="Kurucu", background_color=get_color_from_hex("#8E44AD"), color=(1,1,1,1), bold=True, size_hint_y=None, height=38)
        btn_owner.bind(on_press=lambda x: webbrowser.open("https://guns.lol/dengimisikerim"))
        content.add_widget(btn_owner)

        popup.open()

    def setup_home_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)

        search_box = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.search_input = TextInput(hint_text="Şarkı veya sanatçı adı yazın...", multiline=False, font_size=14)
        search_box.add_widget(self.search_input)

        btn_search = Button(text="Ara", size_hint_x=None, width=90, background_color=get_color_from_hex(self.accent_color), bold=True)
        btn_search.bind(on_press=lambda x: self.start_search())
        search_box.add_widget(btn_search)
        layout.add_widget(search_box)

        tags_layout = BoxLayout(size_hint_y=None, height=36, spacing=6)
        for tag in ["Türkçe Rap", "Drill", "Slow", "Rock"]:
            tb = Button(text=tag, background_color=get_color_from_hex("#181324"), font_size=11, bold=True)
            tb.bind(on_press=lambda btn, t=tag: self.quick_search(t))
            tags_layout.add_widget(tb)
        layout.add_widget(tags_layout)

        self.home_scroll = ScrollView()
        self.home_list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8)
        self.home_list_layout.bind(minimum_height=self.home_list_layout.setter('height'))
        self.home_scroll.add_widget(self.home_list_layout)
        layout.add_widget(self.home_scroll)

        screen.add_widget(layout)

    def quick_search(self, term):
        self.search_input.text = term
        self.start_search()

    def start_search(self):
        query = self.search_input.text.strip()
        if not query:
            return
        self.home_list_layout.clear_widgets()
        self.home_list_layout.add_widget(Label(text="Şarkılar taranıyor...", color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))
        threading.Thread(target=self.run_search_thread, args=(query,), daemon=True).start()

    def run_search_thread(self, query):
        results = self.engine.search_online(query)
        Clock.schedule_once(lambda dt: self.update_song_list(results, self.home_list_layout))

    def update_song_list(self, songs, container, is_offline=False):
        container.clear_widgets()
        self.queue = songs
        if not songs:
            container.add_widget(Label(text="Şarkı bulunamadı.", size_hint_y=None, height=50))
            return

        for idx, song in enumerate(songs):
            item = BoxLayout(size_hint_y=None, height=65, padding=6, spacing=8)
            with item.canvas.before:
                Color(rgba=get_color_from_hex(self.card_bg))
                rect = RoundedRectangle(size=item.size, pos=item.pos, radius=[8, 8, 8, 8])

            item.bind(
                size=lambda s, w, r=rect: setattr(r, 'size', w),
                pos=lambda s, p, r=rect: setattr(r, 'pos', p)
            )

            lbl_info = Label(text=f"[b]{song['title']}[/b]\n[i]{song['artist']}[/i]", markup=True, font_size=12, color=(1,1,1,1), halign='left', valign='middle')
            lbl_info.bind(size=lambda s, w: setattr(s, 'text_size', w))
            item.add_widget(lbl_info)

            if not is_offline:
                btn_dl = Button(text="İndir", size_hint_x=None, width=55, background_color=get_color_from_hex("#201A2E"), font_size=11, bold=True)
                btn_dl.bind(on_press=lambda x, s=song: self.engine.download_song(s))
                item.add_widget(btn_dl)

            btn_play = Button(text="Oynat", size_hint_x=None, width=65, background_color=get_color_from_hex(self.accent_color), bold=True, font_size=11)
            btn_play.bind(on_press=lambda x, s=song, i=idx: self.play_song_action(s, i))
            item.add_widget(btn_play)

            container.add_widget(item)

    def play_song_action(self, song, index):
        self.current_index = index
        self.lbl_now_title.text = f"{song['title']} - {song['artist']}"
        self.btn_play.text = "Durdur"
        threading.Thread(target=lambda: self.engine.play(song), daemon=True).start()
        Clock.schedule_once(lambda dt: self.update_like_button_state(), 0.2)

    def setup_offline_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        layout.add_widget(Label(text="Çevrim Dışı Kitaplık", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        self.offline_scroll = ScrollView()
        self.offline_list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8)
        self.offline_list_layout.bind(minimum_height=self.offline_list_layout.setter('height'))
        self.offline_scroll.add_widget(self.offline_list_layout)
        layout.add_widget(self.offline_scroll)

        screen.add_widget(layout)
        screen.bind(on_enter=self.load_offline_songs)

    def load_offline_songs(self, *args):
        downloads = self.db.get_downloads()
        formatted = [{"title": d[0], "artist": d[1], "file_path": d[2], "thumbnail": d[3], "is_offline": True} for d in downloads]
        self.update_song_list(formatted, self.offline_list_layout, is_offline=True)

    def setup_favorites_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        layout.add_widget(Label(text="Beğenilen Şarkılar", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        self.fav_scroll = ScrollView()
        self.fav_list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8)
        self.fav_list_layout.bind(minimum_height=self.fav_list_layout.setter('height'))
        self.fav_scroll.add_widget(self.fav_list_layout)
        layout.add_widget(self.fav_scroll)

        screen.add_widget(layout)
        screen.bind(on_enter=self.load_favorite_songs)

    def load_favorite_songs(self, *args):
        favs = self.db.get_favorites()
        formatted = [{"title": f[0], "artist": f[1], "web_url": f[2], "thumbnail": f[3], "is_offline": False} for f in favs]
        self.update_song_list(formatted, self.fav_list_layout)

    def setup_stats_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        layout.add_widget(Label(text="Dinleme İstatistikleri", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        self.stats_content = BoxLayout(orientation='vertical', spacing=10)
        layout.add_widget(self.stats_content)
        screen.add_widget(layout)
        screen.bind(on_enter=self.load_stats_data)

    def load_stats_data(self, *args):
        self.stats_content.clear_widgets()
        stats = self.db.get_stats()

        sec = stats["daily"]
        mins = sec // 60
        hrs = mins // 60
        disp = f"{hrs}s {mins % 60}dk" if hrs > 0 else f"{mins}dk"

        self.stats_content.add_widget(Label(text=f"Bugün Dinleme Süresi: {disp}", font_size=14, color=(1,1,1,1)))
        self.stats_content.add_widget(Label(text="En Çok Dinlenen Sanatçılar:", bold=True, color=get_color_from_hex(self.accent_color)))

        for artist, count in stats["top_artists"]:
            self.stats_content.add_widget(Label(text=f"• {artist} ({count} dinleme)", font_size=12, color=(0.8,0.8,0.8,1)))

    def setup_ai_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        layout.add_widget(Label(text="AI Öneri Motoru", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        self.ai_scroll = ScrollView()
        self.ai_list_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8)
        self.ai_list_layout.bind(minimum_height=self.ai_list_layout.setter('height'))
        self.ai_scroll.add_widget(self.ai_list_layout)
        layout.add_widget(self.ai_scroll)

        screen.add_widget(layout)
        screen.bind(on_enter=self.load_ai_recs)

    def load_ai_recs(self, *args):
        recent = self.db.get_recent_tracks(10)
        artists = list(set([r[1] for r in recent])) if recent else ["Top Hits"]
        selected_artist = random.choice(artists)

        self.ai_list_layout.clear_widgets()
        self.ai_list_layout.add_widget(Label(text=f"Önerilen Sanatçı: {selected_artist}", color=get_color_from_hex(self.accent_color), size_hint_y=None, height=30))

        threading.Thread(target=lambda: self.run_ai_search(selected_artist), daemon=True).start()

    def run_ai_search(self, artist):
        results = self.engine.search_online(artist + " hit remix")
        Clock.schedule_once(lambda dt: self.update_song_list(results, self.ai_list_layout))

    def setup_profile_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        layout.add_widget(Label(text="Profil Ayarları", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        layout.add_widget(Label(text="Kullanıcı Adı:", size_hint_y=None, height=25))
        self.profile_input = TextInput(text=self.username, multiline=False, size_hint_y=None, height=45)
        layout.add_widget(self.profile_input)

        btn_save = Button(text="Kaydet", background_color=get_color_from_hex(self.accent_color), bold=True, size_hint_y=None, height=45)
        btn_save.bind(on_press=self.save_profile)
        layout.add_widget(btn_save)

        self.profile_status = Label(text="", size_hint_y=None, height=30)
        layout.add_widget(self.profile_status)

        screen.add_widget(layout)

    def save_profile(self, instance):
        self.username = self.profile_input.text.strip()
        self.db.update_profile(self.username, self.current_theme_name, self.accent_color)
        self.profile_status.text = "Profil güncellendi!"

    def setup_settings_layout(self, screen):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        layout.add_widget(Label(text="Tema ve Görünüm", bold=True, font_size=18, color=get_color_from_hex(self.accent_color), size_hint_y=None, height=40))

        layout.add_widget(Label(text="Tema Seçin:", size_hint_y=None, height=25))
        self.theme_spinner = Spinner(text=self.current_theme_name, values=list(THEMES.keys()), size_hint_y=None, height=45)
        self.theme_spinner.bind(text=self.on_theme_select)
        layout.add_widget(self.theme_spinner)

        screen.add_widget(layout)

    def on_theme_select(self, spinner, text):
        self.apply_theme(text)

    def open_lyrics_popup(self):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        popup = Popup(title="Şarkı Sözleri & Altyazı", content=content, size_hint=(0.85, 0.85))

        if not self.engine.current_song:
            content.add_widget(Label(text="Çalınan şarkı yok."))
            popup.open()
            return

        song = self.engine.current_song
        scroll = ScrollView()
        lyrics_lbl = Label(text="Sözler yükleniyor...", color=(1,1,1,1), size_hint_y=None, halign='center', valign='top')
        lyrics_lbl.bind(size=lambda s, w: setattr(s, 'text_size', (w[0] - 20, None)))
        lyrics_lbl.bind(texture_size=lambda s, t: setattr(s, 'height', t[1]))
        scroll.add_widget(lyrics_lbl)
        content.add_widget(scroll)

        def fetch_lyrics():
            try:
                res = requests.get(f"https://lrclib.net/api/get?track_name={song['title']}&artist_name={song['artist']}", timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    txt = data.get("syncedLyrics") or data.get("plainLyrics")
                    if txt:
                        Clock.schedule_once(lambda dt: setattr(lyrics_lbl, 'text', txt))
                        return
            except Exception:
                pass
            Clock.schedule_once(lambda dt: setattr(lyrics_lbl, 'text', "Altyazı bulunamadı."))

        threading.Thread(target=fetch_lyrics, daemon=True).start()
        popup.open()

    def toggle_play(self, *args):
        self.engine.pause_resume()
        self.btn_play.text = "Oynat" if not self.engine.is_playing else "Durdur"

    def toggle_shuffle(self, *args):
        self.is_shuffle = not self.is_shuffle
        self.btn_shuffle.background_color = get_color_from_hex(self.accent_color) if self.is_shuffle else get_color_from_hex("#181324")

    def toggle_repeat(self, *args):
        self.is_repeat = not self.is_repeat
        self.btn_repeat.background_color = get_color_from_hex(self.accent_color) if self.is_repeat else get_color_from_hex("#181324")

    def play_next(self):
        if not self.queue:
            return
        self.current_index = (self.current_index + 1) % len(self.queue)
        self.play_song_action(self.queue[self.current_index], self.current_index)

    def play_prev(self):
        if not self.queue:
            return
        self.current_index = (self.current_index - 1) % len(self.queue)
        self.play_song_action(self.queue[self.current_index], self.current_index)

    def update_loop(self, dt):
        if self.engine.is_playing:
            pos = self.engine.get_position()
            if pos >= 0:
                self.is_programmatic_change = True
                self.progress_slider.value = min(pos, 1)
                self.is_programmatic_change = False
            if pos >= 0.995 and not getattr(self, "_ended", False):
                self._ended = True
                self.on_track_end()
            elif pos < 0.9:
                self._ended = False

    def on_track_end(self):
        if not self.queue:
            return
        if self.is_repeat:
            idx = self.current_index
        elif self.is_shuffle:
            idx = random.randrange(len(self.queue))
        else:
            idx = (self.current_index + 1) % len(self.queue)
        self.current_index = idx
        self.play_song_action(self.queue[idx], idx)

if __name__ == "__main__":
    EmoryApp().run()
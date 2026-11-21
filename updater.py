# -*- coding: utf-8 -*-
"""
SnipNote 自動更新
GitHub Releases の最新版を確認し、インストーラー(SnipNote-Setup-x.y.z.exe)を
ダウンロード → SHA256SUMS.txt で検証 → サイレント実行して自分を更新する。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from PyQt5.QtCore import QObject, QThread, QTimer, QSettings, pyqtSignal

# ★ 自分のリポジトリ (owner/repo) に変更する
GITHUB_REPO = "hidetako/snipnote"

API_LATEST = "https://api.github.com/repos/%s/releases/latest"
ASSET_RE = re.compile(r"^SnipNote-Setup-(\d+\.\d+\.\d+)\.exe$")
SUMS_NAME = "SHA256SUMS.txt"
USER_AGENT = "SnipNote-Updater"
CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000   # 24時間ごと
FIRST_CHECK_DELAY_MS = 30 * 1000           # 起動30秒後
RETRY_BUSY_MS = 60 * 1000                  # キャプチャ中なら1分後に再試行


def parse_version(text):
    nums = [int(x) for x in re.findall(r"\d+", text or "")[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def is_frozen():
    return bool(getattr(sys, "frozen", False))


class UpdateInfo:
    def __init__(self, version, html_url, asset_name=None, asset_url=None, sha256=None):
        self.version = version
        self.html_url = html_url
        self.asset_name = asset_name
        self.asset_url = asset_url
        self.sha256 = sha256

    @property
    def installable(self):
        return bool(self.asset_url and self.sha256)


def _open(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json, */*"})
    return urllib.request.urlopen(req, timeout=timeout)


def parse_sums(text, name):
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            return parts[0].lower()
    return None


def fetch_latest(repo=GITHUB_REPO, api_base=None):
    url = api_base if api_base else API_LATEST % repo
    with _open(url) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name") or data.get("name") or ""
    assets = data.get("assets") or []
    setup = next((a for a in assets if ASSET_RE.match(a.get("name", ""))), None)
    sums = next((a for a in assets if a.get("name") == SUMS_NAME), None)
    info = UpdateInfo(tag.lstrip("vV"), data.get("html_url", ""))
    if setup:
        info.asset_name = setup["name"]
        info.asset_url = setup["browser_download_url"]
        if sums:
            with _open(sums["browser_download_url"]) as r:
                info.sha256 = parse_sums(r.read().decode("utf-8", "replace"), setup["name"])
    return info


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    tmp = dest + ".part"
    with _open(url, timeout=60) as r, open(tmp, "wb") as f:
        for chunk in iter(lambda: r.read(1024 * 256), b""):
            f.write(chunk)
    os.replace(tmp, dest)
    return dest


def download_dir():
    d = os.path.join(tempfile.gettempdir(), "SnipNoteUpdate")
    os.makedirs(d, exist_ok=True)
    return d


def launch_installer(path):
    """Inno Setup をサイレント実行。インストーラー側が完了後に SnipNote を再起動する。"""
    args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CLOSEAPPLICATIONS"]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, close_fds=True, creationflags=flags)


class UpdateWorker(QThread):
    """バックグラウンドで確認 (+ダウンロード・検証)"""
    no_update = pyqtSignal()
    found = pyqtSignal(object)            # 新版あり（インストール不可 or ダウンロード無効）
    ready = pyqtSignal(object, str)       # 新版あり、検証済みインストーラーのパス
    failed = pyqtSignal(str)

    def __init__(self, current_version, repo=GITHUB_REPO, do_download=True, api_base=None):
        super().__init__()
        self.current = current_version
        self.repo = repo
        self.do_download = do_download
        self.api_base = api_base

    def run(self):
        try:
            info = fetch_latest(self.repo, self.api_base)
            if parse_version(info.version) <= parse_version(self.current):
                self.no_update.emit()
                return
            if not (self.do_download and info.installable):
                self.found.emit(info)
                return
            dest = os.path.join(download_dir(), info.asset_name)
            if not (os.path.exists(dest) and sha256_file(dest) == info.sha256):
                download(info.asset_url, dest)
            actual = sha256_file(dest)
            if actual != info.sha256:
                os.remove(dest)
                raise ValueError("SHA256 が一致しません (期待 %s… / 実際 %s…)" % (info.sha256[:12], actual[:12]))
            self.ready.emit(info, dest)
        except Exception as ex:  # ネットワーク不通などは通知のみ
            self.failed.emit("%s: %s" % (type(ex).__name__, ex))


class AutoUpdater(QObject):
    """
    アプリ側の司令塔。
    - 常駐時: 起動30秒後と24時間ごとに確認
    - 検証済みインストーラーが用意できたら、キャプチャ中でなければ実行して終了
    """
    status = pyqtSignal(str, str, bool)   # (title, message, is_warning)
    quit_requested = pyqtSignal()

    def __init__(self, current_version, is_busy, repo=GITHUB_REPO, parent=None):
        super().__init__(parent)
        self.current = current_version
        self.is_busy = is_busy
        self.repo = repo
        self.settings = QSettings("SnipNote", "SnipNote")
        self.worker = None
        self.pending = None   # (info, path)
        self.manual = False
        self.last_found = None
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_INTERVAL_MS)
        self.timer.timeout.connect(lambda: self.check(manual=False))

    # ---- 設定 ----
    @property
    def enabled(self):
        return self.settings.value("auto_update", True, type=bool)

    @enabled.setter
    def enabled(self, v):
        self.settings.setValue("auto_update", bool(v))
        if v and is_frozen():
            self.timer.start()
        else:
            self.timer.stop()

    def start(self):
        if is_frozen() and self.enabled:
            QTimer.singleShot(FIRST_CHECK_DELAY_MS, lambda: self.check(manual=False))
            self.timer.start()

    # ---- 確認 ----
    def check(self, manual=False):
        if self.worker is not None and self.worker.isRunning():
            return
        self.manual = manual
        self.worker = UpdateWorker(self.current, self.repo, do_download=is_frozen())
        self.worker.no_update.connect(self._on_none)
        self.worker.found.connect(self._on_found)
        self.worker.ready.connect(self._on_ready)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_none(self):
        if self.manual:
            self.status.emit("SnipNote", "最新版です (v%s)" % self.current, False)

    def _on_found(self, info):
        self.last_found = info
        how = "ダウンロードページを開くにはクリック" if not is_frozen() else "インストーラーが見つからないため手動更新してください"
        self.status.emit("SnipNote 新バージョン v%s" % info.version, how, False)

    def _on_ready(self, info, path):
        self.pending = (info, path)
        self.try_install()

    def _on_failed(self, msg):
        if self.manual:
            self.status.emit("SnipNote 更新確認に失敗", msg, True)

    def try_install(self):
        if not self.pending:
            return
        if self.is_busy():
            QTimer.singleShot(RETRY_BUSY_MS, self.try_install)
            return
        info, path = self.pending
        self.pending = None
        self.status.emit("SnipNote", "v%s に更新します。数秒後に再起動します。" % info.version, False)
        QTimer.singleShot(3000, lambda: self._run(path))

    def _run(self, path):
        try:
            launch_installer(path)
        except Exception as ex:
            self.status.emit("SnipNote 更新に失敗", str(ex), True)
            return
        self.quit_requested.emit()

    def open_download_page(self):
        if self.last_found and self.last_found.html_url:
            import webbrowser
            webbrowser.open(self.last_found.html_url)

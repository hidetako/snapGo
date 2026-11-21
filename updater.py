# -*- coding: utf-8 -*-
"""
SnipNote 閾ｪ蜍墓峩譁ｰ
GitHub Releases 縺ｮ譛譁ｰ迚医ｒ遒ｺ隱阪＠縲√う繝ｳ繧ｹ繝医・繝ｩ繝ｼ(SnipNote-Setup-x.y.z.exe)繧・繝繧ｦ繝ｳ繝ｭ繝ｼ繝・竊・SHA256SUMS.txt 縺ｧ讀懆ｨｼ 竊・繧ｵ繧､繝ｬ繝ｳ繝亥ｮ溯｡後＠縺ｦ閾ｪ蛻・ｒ譖ｴ譁ｰ縺吶ｋ縲・"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from PyQt5.QtCore import QObject, QThread, QTimer, QSettings, pyqtSignal

# 笘・閾ｪ蛻・・繝ｪ繝昴ず繝医Μ (owner/repo) 縺ｫ螟画峩縺吶ｋ
GITHUB_REPO = "あなたのGitHubユーザー名/snipnote"

API_LATEST = "https://api.github.com/repos/%s/releases/latest"
ASSET_RE = re.compile(r"^SnipNote-Setup-(\d+\.\d+\.\d+)\.exe$")
SUMS_NAME = "SHA256SUMS.txt"
USER_AGENT = "SnipNote-Updater"
CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000   # 24譎る俣縺斐→
FIRST_CHECK_DELAY_MS = 30 * 1000           # 襍ｷ蜍・0遘貞ｾ・RETRY_BUSY_MS = 60 * 1000                  # 繧ｭ繝｣繝励メ繝｣荳ｭ縺ｪ繧・蛻・ｾ後↓蜀崎ｩｦ陦・

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
    """Inno Setup 繧偵し繧､繝ｬ繝ｳ繝亥ｮ溯｡後ゅう繝ｳ繧ｹ繝医・繝ｩ繝ｼ蛛ｴ縺悟ｮ御ｺ・ｾ後↓ SnipNote 繧貞・襍ｷ蜍輔☆繧九・""
    args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CLOSEAPPLICATIONS"]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, close_fds=True, creationflags=flags)


class UpdateWorker(QThread):
    """繝舌ャ繧ｯ繧ｰ繝ｩ繧ｦ繝ｳ繝峨〒遒ｺ隱・(+繝繧ｦ繝ｳ繝ｭ繝ｼ繝峨・讀懆ｨｼ)"""
    no_update = pyqtSignal()
    found = pyqtSignal(object)            # 譁ｰ迚医≠繧奇ｼ医う繝ｳ繧ｹ繝医・繝ｫ荳榊庄 or 繝繧ｦ繝ｳ繝ｭ繝ｼ繝臥┌蜉ｹ・・    ready = pyqtSignal(object, str)       # 譁ｰ迚医≠繧翫∵､懆ｨｼ貂医∩繧､繝ｳ繧ｹ繝医・繝ｩ繝ｼ縺ｮ繝代せ
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
                raise ValueError("SHA256 縺御ｸ閾ｴ縺励∪縺帙ｓ (譛溷ｾ・%s窶ｦ / 螳滄圀 %s窶ｦ)" % (info.sha256[:12], actual[:12]))
            self.ready.emit(info, dest)
        except Exception as ex:  # 繝阪ャ繝医Ρ繝ｼ繧ｯ荳埼壹↑縺ｩ縺ｯ騾夂衍縺ｮ縺ｿ
            self.failed.emit("%s: %s" % (type(ex).__name__, ex))


class AutoUpdater(QObject):
    """
    繧｢繝励Μ蛛ｴ縺ｮ蜿ｸ莉､蝪斐・    - 蟶ｸ鬧先凾: 襍ｷ蜍・0遘貞ｾ後→24譎る俣縺斐→縺ｫ遒ｺ隱・    - 讀懆ｨｼ貂医∩繧､繝ｳ繧ｹ繝医・繝ｩ繝ｼ縺檎畑諢上〒縺阪◆繧峨√く繝｣繝励メ繝｣荳ｭ縺ｧ縺ｪ縺代ｌ縺ｰ螳溯｡後＠縺ｦ邨ゆｺ・    """
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

    # ---- 險ｭ螳・----
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

    # ---- 遒ｺ隱・----
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
            self.status.emit("SnipNote", "譛譁ｰ迚医〒縺・(v%s)" % self.current, False)

    def _on_found(self, info):
        self.last_found = info
        how = "繝繧ｦ繝ｳ繝ｭ繝ｼ繝峨・繝ｼ繧ｸ繧帝幕縺上↓縺ｯ繧ｯ繝ｪ繝・け" if not is_frozen() else "繧､繝ｳ繧ｹ繝医・繝ｩ繝ｼ縺瑚ｦ九▽縺九ｉ縺ｪ縺・◆繧∵焔蜍墓峩譁ｰ縺励※縺上□縺輔＞"
        self.status.emit("SnipNote 譁ｰ繝舌・繧ｸ繝ｧ繝ｳ v%s" % info.version, how, False)

    def _on_ready(self, info, path):
        self.pending = (info, path)
        self.try_install()

    def _on_failed(self, msg):
        if self.manual:
            self.status.emit("SnipNote 譖ｴ譁ｰ遒ｺ隱阪↓螟ｱ謨・, msg, True)

    def try_install(self):
        if not self.pending:
            return
        if self.is_busy():
            QTimer.singleShot(RETRY_BUSY_MS, self.try_install)
            return
        info, path = self.pending
        self.pending = None
        self.status.emit("SnipNote", "v%s 縺ｫ譖ｴ譁ｰ縺励∪縺吶よ焚遘貞ｾ後↓蜀崎ｵｷ蜍輔＠縺ｾ縺吶・ % info.version, False)
        QTimer.singleShot(3000, lambda: self._run(path))

    def _run(self, path):
        try:
            launch_installer(path)
        except Exception as ex:
            self.status.emit("SnipNote 譖ｴ譁ｰ縺ｫ螟ｱ謨・, str(ex), True)
            return
        self.quit_requested.emit()

    def open_download_page(self):
        if self.last_found and self.last_found.html_url:
            import webbrowser
            webbrowser.open(self.last_found.html_url)



# SnapGo - 画面キャプチャ＋その場で書き込み（Windows）

画面全体を一瞬で凍結し、ドラッグで範囲を選ぶと**その場に**ツールバーが出て、
ペン・矢印・矩形・文字・番号・モザイクを直接書き込めます。
Enter でクリップボードへ、Ctrl+S で PNG 保存。別ウィンドウを開かず完結します。

## インストール（配布版・推奨）

GitHub Releases から `SnapGo-Setup-x.y.z.exe` をダウンロードして実行。
ユーザー単位インストール（`%LOCALAPPDATA%\Programs\SnapGo`）のため管理者権限は不要です。

* インストール時に「サインイン時に自動起動」をチェックすると、以後 PrtSc でいつでも起動します。
* アンインストールは Windows の「アプリと機能」から。

## 旧名 SnipNote からの移行

v1.1.x は「SnipNote」という名前で配布していました。v1.2.0 以降は SnapGo です。
SnipNote 1.1.x は新しい名前のインストーラーを自動更新で取り込めないため、
一度だけ `SnapGo-Setup-x.y.z.exe` を手動で実行してください。
旧フォルダー・スタートアップ登録・常駐プロセスはインストーラーが片付けます。

## 自動更新

* 常駐中、起動 30 秒後と 24 時間ごとに GitHub Releases の最新版を確認します。
* 新版があればインストーラーをバックグラウンドで取得し、Release 添付の `SHA256SUMS.txt` で検証します。
  検証に失敗した場合はインストールしません。
* キャプチャ中でなければトレイに「v x.y.z に更新します」と出た 3 秒後にサイレント更新し、自動で再起動します。
* トレイメニューの「自動更新」で ON/OFF、「今すぐ更新を確認」で手動確認できます。
  `--no-update` 起動でも無効化できます。
* ソースから実行している場合は確認のみ行い、通知をクリックするとダウンロードページが開きます。

## 開発者向け: ビルドとリリース

### 必要なもの（Windows）

```powershell
winget install JRSoftware.InnoSetup
```

```powershell
pip install -r requirements.txt pyinstaller
```

### ローカルビルド

```powershell
cd C:\dev\snapgo
```

```powershell
.\build.ps1
```

`dist\SnapGo-Setup-x.y.z.exe` と `dist\SHA256SUMS.txt` ができます。

### リリース手順（GitHub Actions で自動ビルド）

1. `updater.py` の `GITHUB_REPO` と `installer\snapgo.iss` の `AppURL` を自分の `owner/repo` にする（初回のみ）
2. `snapgo.py` の `__version__` を上げる（例 `"1.2.0"`）
3. コミットして、同じ番号のタグを push

```powershell
git commit -am "v1.2.0"
```

```powershell
git tag v1.2.0
```

```powershell
git push origin main --tags
```

`.github/workflows/release.yml` が windows-latest 上で exe とインストーラーを作り、
Release に `SnapGo-Setup-1.2.0.exe` と `SHA256SUMS.txt` を添付します。
タグと `__version__` が食い違うとビルドは失敗します。
公開後、常駐中の各 PC は次回確認時（最長 24 時間後）に自動更新されます。

## ソースから実行する場合（PowerShell、1行ずつ）

```powershell
cd C:\dev\snapgo
```

```powershell
pip install -r requirements.txt
```

## PrintScreen キーで起動する（推奨の使い方）

`install_startup.bat` をダブルクリックすると、

1. スタートアップに SnapGo のショートカットを登録（サインイン時に自動常駐）
2. その場で常駐を開始

以後、**PrtSc を押すと SnapGo が立ち上がります**。解除は `uninstall_startup.bat`。

### PrtSc を他の機能に取られている場合

Windows 11 は既定で PrtSc に Snipping Tool を割り当てています。
SnapGo は Snipping Tool に先取りされていても低レベルキーボードフックで PrtSc を横取りしますが、
確実に動かすため、以下を OFF にしてください。

* 設定 > アクセシビリティ > キーボード > 「PrintScreen キーを使用して画面キャプチャを開く」 → OFF

PowerShell で行う場合（1行、実行後にサインインし直し）:

```powershell
Set-ItemProperty -Path 'HKCU:\Control Panel\Keyboard' -Name PrintScreenKeyForSnippingEnabled -Value 0
```

* OneDrive が PrtSc の画像を自動保存する場合: OneDrive 設定 > 同期とバックアップ > 「作成したスクリーンショットを OneDrive に保存する」 → OFF
* Alt+PrtSc（アクティブウィンドウのコピー）は横取りせず、Windows 標準のまま動きます。

常駐中はトレイアイコンのツールチップに登録方式が表示されます。
`RegisterHotKey` なら競合なし、`KeyboardHook` なら他アプリから横取りして動作中です。

## 使い方

| 起動方法 | コマンド |
|---|---|
| PrtSc で起動（常駐） | install_startup.bat、または `pythonw snapgo.py --tray` |
| 1回だけキャプチャ | `pythonw snapgo.py` （または snip_once.bat） |
| ホットキー変更 | `pythonw snapgo.py --tray --hotkey ctrl+shift+a` |
| 保存先変更 | `pythonw snapgo.py --tray --dir D:\captures` |

既定の保存先: `%USERPROFILE%\Pictures\Screenshots\snip_YYYYMMDD_HHMMSS.png`

### 操作

| 操作 | 内容 |
|---|---|
| ドラッグ | 範囲選択（クリックのみ → そのモニター全体） |
| S / P / H / L / A / R / E / T / N / M | 選択移動 / ペン / 蛍光 / 直線 / 矢印 / 矩形 / 楕円 / 文字 / 番号 / モザイク |
| ツールバー | 色 8 色、太さスライダー、「↶ 戻る」「進む ↷」（押せないときは灰色）、コピー、保存、✕ |
| Ctrl+Z / Ctrl+Y | 元に戻す / やり直し |
| Enter | コピーして閉じる（確認が出るので、もう一度 Enter で実行） |
| Ctrl+C | コピーして閉じる（即時） |
| Ctrl+S | PNG 保存（＋コピー）して閉じる |
| Ctrl+Shift+S | 保存先を指定して保存 |
| Esc | キャンセル（書き込みがあれば破棄するか確認） |
| 右クリック | メニュー（コピー / 保存 / 範囲を選び直す / 元に戻す / 破棄） |
| F12 | 表示中の画面そのもの（選択枠・ツールバー込み）を PNG 保存。紹介用スクリーンショット向け |

* 文字ツール: クリック→入力→Enter で確定、Esc で取り消し。
* モザイク: 患者名・ID など個人情報を隠す用途を想定。元画像を粗くするので復元不可。
* 「選択」ツールで枠内をドラッグすると枠を移動、枠外をドラッグすると選び直し。

### 手動でスタートアップ登録する場合

1. `Win + R` → `shell:startup`
2. 開いたフォルダに `run_tray.bat` のショートカットを置く

## 既知の制限・注意

* 動作確認は Linux 上の仮想ディスプレイで描画ロジックと更新ロジック（ダウンロード・検証・改ざん検出）を実施。
  Windows 実機での **ホットキー・マルチモニター・DPI・クリップボード・インストーラー** は未検証。
  初回は `build.ps1` をローカルで実行し、インストーラーの動作を確認してからタグを push してください。
* 自動更新は GitHub Releases が前提です。リポジトリが private の場合、API に認証が必要なため
  更新確認は失敗します（public リポジトリにするか、別配布サーバーへ `updater.py` の URL を変更）。
* 高 DPI (125%〜) 環境ではツールバー文字が小さく見える場合があります。
  その場合は `snapgo.py` 先頭の `QT_ENABLE_HIGHDPI_SCALING` を `"1"` にして試してください。
* ホットキー登録とフックの両方に失敗した場合はトレイ通知が出ます。
  `--hotkey ctrl+shift+a` など別のキーを指定してください。
* 管理者権限で動くアプリ（タスクマネージャー等）が前面のときは、
  通常権限の SnapGo には PrtSc が届きません（Windows の仕様）。
* 全画面排他モードのゲーム等はキャプチャできません。

## 構成

* `snapgo.py` 本体（依存は PyQt5 のみ）
* `updater.py` 自動更新（GitHub Releases 参照、SHA256 検証）
* `build.ps1` Windows ビルド（PyInstaller → Inno Setup → SHA256SUMS.txt）
* `installer/snapgo.iss` Inno Setup スクリプト
* `.github/workflows/release.yml` タグ push で Release 自動作成
* `assets/snapgo.ico` アイコン
* `install_startup.bat` スタートアップ登録 + 常駐開始（PrtSc で起動）
* `uninstall_startup.bat` 登録解除 + 停止
* `run_tray.bat` 常駐起動のみ
* `snip_once.bat` 単発起動

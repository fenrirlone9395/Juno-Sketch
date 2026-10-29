# JUNO Sketch v0.1.1

JUNO-DS用の小さなPython/Tkinter MIDIシーケンサーです。16トラック、ピアノロール、通常／三連符Grid、Slip、Velocity、SMF Type 1、JSONプロジェクトを実装しています。

## Macでの起動

Python 3.12とTkを推奨します。python-rtmidi 1.5.8のmacOS用ビルド済みwheelを使える構成です。Python 3.14ではソースビルドが必要になる場合があります。macOS付属の古いPythonは対象外です。Apple SiliconではPythonと依存パッケージのアーキテクチャを揃えてください。

初回の依存導入と開発実行：

```bash
cd juno-sequencer
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

内部プレビューはmacOS標準AudioToolboxのDLSシンセを使用します。FluidSynth、SoundFontのダウンロードは不要です。JUNO-DSの音色を再現するものではなく、Program Changeに対応するGM相当の確認音源です。内部プレビューではJUNO用のBank Selectを無視します。

## .appの作成

Mac上で `scripts/build_macos.command` を実行します。Finderでのダブルクリックも可能です。初回はPython環境とネット接続が必要です。

```bash
bash scripts/build_macos.command
```

`dist/JunoSketch.app` ができます。これをApplicationsへコピーすると、以後はターミナルを開かずダブルクリックで起動できます。Python、mido、rtmidi、TkはPyInstallerが同梱し、内部音源はmacOSのフレームワークを利用します。

ビルドは対象Mac上で行ってください。LinuxからmacOS .appをクロスビルドする構成ではありません。署名・公証・他のMac向け配布インストーラーは含みません。必要なら `JUNO_PYTHON=/path/to/python3 bash scripts/build_macos.command` でPythonを指定できます。

## 操作

- 左で16トラックを選択。Channelは1〜16、Programは1〜128表示（内部MIDI値は0始まり）。Bankは0〜127。
- 設定変更後は「設定を適用・音色送信」。Default Velocityもここで変更します。
- 空白をダブルクリックして作成。ノート中央をドラッグして時刻／音程移動、右端7pxで長さ変更。
- Shiftクリックで選択を追加／解除。空白から囲んで複数選択。Shift＋囲みで追加。
- Delete／Backspaceで選択ノートを削除。右クリックで対象ノートを削除。
- Grid／Slipと分解能は上部。1/4、1/8、1/16、1/32とそれぞれのT（三連符）。同じトラック内で混在できます。
- Velocityレーンのバーを上下ドラッグ。複数選択時は選択全体に同じ値を設定します。
- Spaceで再生／停止。ルーラークリックで開始位置、`|◀`で先頭。
- BPMを入力して「適用」。入力欄にフォーカス中のSpaceやDeleteは編集操作になります。
- Cmd+Z／Cmd+Shift+ZでUndo／Redo。Cmd+S保存、Cmd+O読込、Cmd+N新規。メニューからも利用可能。
- ホイールで上下、Shift＋ホイールまたは下部スクロールバーで左右移動。
- 右方向は最低8小節。末尾のノートに合わせて自動延長します。全128音の音域。

## JUNO-DS接続

1. JUNO-DSをUSB接続し、macOSのAudio MIDI設定等で認識されることを確認。
2. 本体側で16パートが受信できるPerformanceと各パートのMIDI受信チャンネルを設定。
3. 出力をJUNO-DSへ切替。「ポート更新」を押し、JUNO-DSのポートを選択。
4. 対象トラックのBank MSB／LSB／Programを本体のMIDI Implementation／音色表に合わせて設定し、「設定を適用・音色送信」。

ポート選択肢はmacOSのMIDIポート一覧です。自動で最初のポートへ送信することはありません。意図したJUNO-DSポートを選んでください。USBドライバーの要否は本体設定／OSとの組合せに依存します。本体の音色名データベースや固有SysExは含みません。同一チャンネルに複数トラックを割り当てると音色設定等を共有します。独立したパートには異なるチャンネルを割り当ててください。

## 保存と読込

独自形式は `.juno.json`。ノート、トラック設定、BPM、テンポ情報、グリッド、出力ポート、選択トラック、ウィンドウ位置／大きさ、スクロールを保存します。新規・読込・終了時には未保存の編集を確認します。プロジェクトは一時ファイルを経由して置換します。

SMF出力はType 1、PPQ 960。テンポ／拍子のconductor＋16のMIDIトラック（計17 SMFチャンク）です。MIDIトラックのBank MSB→LSB→Programを先頭に書き込みます。ノート、Velocity、チャンネル、途中のCC／Program／Pitch Bend／Aftertouchも保持します。読込では元のPPQを960に変換します。Type 0も読み込めますが、16を超える「元トラック×チャンネル」があるファイルとType 2／SMPTE divisionは明示的に拒否します。元の解像度が960の約数でなければ1tick未満の丸めが生じます。

エディターは4/4表示です。インポートした他拍子は警告し、SMFには拍子を保持します。途中のテンポ変更は再生・再出力できます。BPMを変更するとテンポマップは一定テンポに置き換えます。SysEx、歌詞など対象外のメタイベントは保持しません。空の元トラックの配置や同音の重なりの識別など、あらゆるSMFの完全な往復は保証しません。

## 構成

- `models/project.py`：Project／Track／Note、PPQ、グリッド
- `ui/main_window.py`：アプリ、トラック一覧、保存、出力切替
- `ui/piano_roll.py`：ピアノロール、選択、ドラッグ、Velocity
- `midi/output.py`：MidiOutputの抽象インターフェース
- `midi/internal_preview.py`：macOSシステム音源
- `midi/juno_ds.py`：mido／rtmidiによるJUNO出力
- `midi/player.py`：独立スレッドと単調増加時計による再生
- `midi/smf.py`：SMF読み書き
- `services/`：Undo／Redo、JSON保存

再生は開始時のスナップショットです。再生中の編集は次回再生から反映します。タイミングは絶対時刻を基準に待機し、イベントごとのsleep誤差の累積を避けます。OS／USBのジッターやレイテンシーを保証するハードリアルタイム実装ではありません。停止と出力切替時にSustain Off／All Notes Off／All Sound Offを全チャンネルに送信します。将来の出力はMidiOutputを実装して追加できますが、現状は2系統だけです。

## テスト

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

`tests/` はデータ／保存往復／タイミング変換／モック出力／編集ハンドラーを検証します。OS音源や実USB接続の代わりにはなりません。Macでの最終確認は `ACCEPTANCE.md` に記載しています。

例外はダイアログ／ステータスで表示します。ログは `~/Library/Logs/JunoSketch/app.log`。

## 参考にした公式仕様

- Apple AudioToolbox DLS Synth: https://developer.apple.com/documentation/audiotoolbox/kaudiounitsubtype_dlssynth
- Apple MusicDeviceMIDIEvent: https://developer.apple.com/documentation/audiotoolbox/musicdevicemidievent(_:_:_:_:_:)
- Mido SMF: https://mido.readthedocs.io/en/stable/files/midi.html
- PyInstaller macOS/windowed: https://www.pyinstaller.org/en/stable/usage.html

`examples/four-bars.juno.json` と `.mid` は16分音符／三連符の混在した4小節の確認用です。

## v0.1.1：レイヤー表示と全体表示

上部の2段目に表示切替を追加しました。

- `Piano Roll`＋「他トラックをレイヤー表示」：他の15トラックを暗めのトラック色で表示します。チェックを外すと現在のトラックだけ表示します。
- 背景ノートは参照用です。選択、ドラッグ、削除、Velocity編集は現在のトラックだけに適用します。背景ノート上のダブルクリックは現在のトラックへのノート作成になります。
- トラックごとの色は左の一覧、編集ノート、全体表示で共通です。選択ノートは従来どおり明るい黄色です。
- `All Tracks`：16トラックを縦に並べ、すべてのノートと再生カーソルを表示します。各レーンの上下はそのトラック内の音域を相対表示します。正確な音高の比較はピアノロールのレイヤー表示を使ってください。
- 全体表示は参照専用です。クリックでトラック選択、ダブルクリックでそのトラックの編集画面へ戻ります。Delete／Backspaceではノートを削除しません。
- Spaceで従来どおり全トラックを再生／停止します。表示・トラックの切替で再生は止まりません。「全体表示で再生位置に追従」で横方向の自動スクロールを切り替えます。ルーラーで再生開始位置を指定できます。
- レイヤー表示の有無、表示モード、追従、全体表示の横スクロール位置はプロジェクトに保存します。従来のv0.1プロジェクトも読み込めます。
- ピアノロールの横スクロール範囲は全トラックの末尾に合わせます。

### 既存環境の更新

アプリを終了し、ZIP内のソースを元の `juno-sequencer` フォルダへ上書きしてください。`.venv` と自作の `.juno.json`／`.mid` は残します。この更新では追加パッケージは不要です。

起動確認：

```bash
.venv/bin/python main.py
```

既にビルドできている環境では、その仮想環境で再ビルドできます。

```bash
.venv/bin/python -m PyInstaller --noconfirm JunoSketch.spec
```

`dist/JunoSketch.app` を更新してください。

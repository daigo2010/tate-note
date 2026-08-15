# 縦書きノート (tate-note)

Ubuntu 用のシンプルな縦書きテキストエディタです。GTK3 + WebKit2GTK 上で、
CSS の `writing-mode: vertical-rl` を使って本格的な縦書き表示・編集を行います。

## 機能

- 縦書き（右から左、上から下）でのテキスト編集
- 新規 / 開く / 保存 / 名前を付けて保存（プレーンテキスト .txt）
- 文字サイズの拡大・縮小
- 文字数カウント表示
- 未保存の変更がある場合の確認ダイアログ

## 設定

ヘッダーバーのメニューボタンから切り替えます。設定は
`~/.config/tate-note/settings.json` に保存され、次回起動時に復元されます。

| 設定 | 既定 | 内容 |
| --- | --- | --- |
| 行番号を表示 | off | 各行の先頭（列の上端）に行番号を表示 |
| 改行を文字数に含める | on | 文字数カウントに改行を数えるかどうか |
| 空白・タブ・改行を表示 | off | 半角・全角スペース、タブ、改行を記号で可視化 |

表示上の装飾はすべて CSS の擬似要素と背景で描いており、保存されるファイルの
内容には一切含まれません。

## 動作環境

Ubuntu 22.04 以降（GTK3 + WebKit2GTK 4.1 系、または 4.0 系）。

## インストール（.deb パッケージ）

```sh
./build-deb.sh            # dist/tate-note_1.0.0_all.deb を生成
sudo apt install ./dist/tate-note_1.0.0_all.deb
```

apt が依存パッケージ（python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 など）を
自動的に解決してインストールします。

インストール後はアプリケーション一覧から「縦書きノート」を起動するか、
ターミナルから `tate-note` （または `tate-note ファイル名.txt`）で起動できます。

アンインストール:

```sh
sudo apt remove tate-note
```

## 開発 / 動作確認（インストールせずに実行）

```sh
python3 src/tate-note
```

`src/assets` が隣にあればそちらを優先して読み込むため、インストール前でも
そのまま動作確認できます。

## 依存パッケージ（開発時）

```sh
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

## パッケージ構成

```
src/tate-note        本体（Python / PyGObject）
src/assets/          縦書きエディタの HTML/CSS/JS
src/tate-note.svg    アイコン
packaging/           .desktop ファイルと dpkg control テンプレート
build-deb.sh         .deb ビルドスクリプト
```

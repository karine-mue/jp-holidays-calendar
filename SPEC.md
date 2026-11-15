# 仕様: build_calendar.py（内閣府・祝日CSV → ICS）

## 目的
内閣府が公開する「国民の祝日」CSV を取得し、Google カレンダー等に購読できる ICS と、再利用しやすい UTF-8 CSV を生成する。正確性は「内閣府の公式CSVをそのまま使う」ことで担保する（祝日計算ロジックは自前で実装しない）。

## データ源（実測済み 2026-11-15）
- URL: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
- 文字コード: Shift_JIS 系（実装は cp932 でデコードする。公式表記は Shift_JIS だが、cp932 が実データに対して安全な superset）
- ヘッダー: `国民の祝日・休日月日,国民の祝日・休日名称`
- 日付形式: `YYYY/M/D`（例 2026/1/1）
- 収録範囲: 1955/1/1 〜 2027/11/23、全1,067行（取得時点）。振替休日・国民の休日も行として含まれるが、名称はいずれも「休日」で収録されている（実測で判明：名称「振替休日」「国民の休日」の行は存在しない。「休日」は全期間で116行）。変換は公式名称のまま行う。

## 実装要件
- Python 標準ライブラリのみ。
- 関数を import 可能に分ける:
  - `parse_holidays(text: str) -> list[tuple[datetime.date, str]]` — CSVテキスト（cp932デコード済み文字列）を受け取り、日付昇順・重複除去済みのリストを返す。ヘッダー行は期待値と一致するか検証し、不一致ならエラーにする（黙って読み飛ばさない）。日付は `YYYY/M/D` の形を厳密に照合する（全角数字・アンダースコア・符号つきは不可）。名称は前後の空白のみ除去し、公式名称自体は変更しない。
  - `build_ics(rows, dtstamp: str) -> str` — ICS文字列を返す。dtstamp は呼び出し側が渡す（テストで固定できるように）。
  - `build_utf8_csv(rows) -> str` — `date,name` ヘッダー付き、ISO日付（YYYY-MM-DD）のCSV文字列。
  - `main()` — CLI。
- CLI 引数: `--from-year`（int、デフォルトは今年−1。この年以降の行だけ出力。「今年」は Asia/Tokyo 基準。範囲は 1900–2100）、`--source`（URL またはローカルパス、デフォルトは上記公式URL。http/https で始まらないものはローカルパスとして扱い、存在しなければエラー）、`--out-dir`（デフォルトはカレントディレクトリ）。
- 要 Python 3.10 以上（型ヒント記法と zoneinfo を使用）。
- ICS の要件:
  - `BEGIN:VCALENDAR` / `VERSION:2.0` / `PRODID:-//jp-holidays-calendar//JA//` / `CALSCALE:GREGORIAN` / `METHOD:PUBLISH`
  - カレンダー名: `X-WR-CALNAME:日本の祝日（内閣府）`
  - 各 VEVENT: `UID:syukujitsu-YYYYMMDD@jp-holidays-calendar`（日付で一意・安定）、`DTSTAMP`（引数の値）、`DTSTART;VALUE=DATE:YYYYMMDD`、`DTEND;VALUE=DATE:` 翌日、`SUMMARY:名称`、`TRANSP:TRANSPARENT`（終日・時間をブロックしない）
  - 行末は CRLF（RFC 5545）。
- 出力ファイル: `syukujitsu.ics` と `syukujitsu.csv`（UTF-8版）を out-dir に書く。書き込みは一時ファイル経由の原子的置換で行う。
- エラー処理: 取得失敗やパース不能行があれば例外で落とす（黙って欠落させない）。フィルタ後の件数が0件の場合もエラー終了し、空のカレンダーで既存の出力を上書きしない。

## テスト観点（Muse 側で実施）
- フィクスチャCSVでの parse / ICS / CSV 変換の正確さ（件数、DTEND=翌日、UID一意、CRLF、TRANSPARENT）。
- 実データ: 2026年が18件、2026/1/1=元日、2027/11/23=勤労感謝の日 が ICS に含まれる。
- from-year フィルタの境界。

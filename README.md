# 日本の祝日カレンダー（内閣府データ）

内閣府が公開する「国民の祝日」CSV から生成した、日本の祝日の iCalendar（.ics）です。
Google カレンダーの標準の祝日カレンダーと違い、**内閣府の公式データに載っている祝日だけ**が入ります。

## 使い方（Google カレンダーに購読）

1. このリポジトリの `syukujitsu.ics` の raw URL をコピーする
2. Google カレンダー → 「他のカレンダー」→「URL を追加」に貼る

購読しておけば、このリポジトリ側が更新されると自動で反映されます（Google 側の取得間隔に依存します）。

## ファイル

- `syukujitsu.ics` — 祝日カレンダー本体（終日イベント、時間をブロックしない設定）
- `syukujitsu.csv` — 同じ内容の UTF-8 CSV（日付は ISO 形式）
- `build_calendar.py` — 生成スクリプト（Python 標準ライブラリのみ）
- `test_build_calendar.py` — テスト

## データ源

- 内閣府「国民の祝日」CSV: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
- 祝日の計算は自前で行わず、公式CSVをそのまま変換しています。
- 注意：内閣府CSVでは、振替休日・国民の休日はどちらも名称「休日」として収録されています（例：2026/5/6、2026/9/22）。このカレンダーでも公式の表記のまま「休日」と表示されます。

## 更新

GitHub Actions が毎月1回、公式CSVを取得し直して差分があれば再生成・コミットします。
手元で再生成する場合:

```sh
python3 build_calendar.py            # 公式CSVを取得して生成
python3 build_calendar.py --from-year 2026 --source ./syukujitsu_raw.csv
```

## ライセンス

生成データは内閣府の公開データに基づきます。コードは MIT ライセンスです。

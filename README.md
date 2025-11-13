# review-automation

## 使用方法
### 事前準備
* プロジェクトのActions用のSecret変数にGEMINI_API_KEYを設定
### 実行方法
* プッシュにより自動起動
   * Github Actionsを使用しているため、自動で呼び出される
   * geminiを呼び出し、レビュー結果を取得する
   * /reviewに日付単位でレビュー結果をファイル出力する

### 参考
* 関連リポジトリ
   * DropboxからGitへプッシュするバッチのリポジトリ
      * [https://github.com/m-Inmoat/dbx-git-sync](https://github.com/m-Inmoat/dbx-git-sync)
   * GitからDropboxへ対象ディレクトリを同期するバッチのリポジトリ
      * [https://github.com/m-Inmoat/git-dbx-sync](https://github.com/m-Inmoat/git-dbx-sync)

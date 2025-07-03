# pythonのインストール
https://www.python.org/downloads/

# node.jsのインストール
https://nodejs.org/

# 仮想環境フォルダの新規作成
python -m venv venv

# 仮想環境のアクティベーション
.\venv\Scripts\activate

# ライブラリのインストール用 pip最新版インストール
python.exe -m pip install --upgrade pip

# ライブラリのインストール
pip install -r requirements.txt


# OpenAI API keyの入手
https://platform.openai.com/docs/overview


# CSVファイルの形式は以下の通りです：
# 1列目: そのまま訳す：term,  翻訳指定：replace, 　翻訳しない: remove
# 2列目: 原文
# 3列目: 翻訳語　（翻訳しない場合は空欄）


# その他
Localでの使用を前提としているため、SSLは非対応

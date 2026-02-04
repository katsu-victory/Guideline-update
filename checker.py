import requests
from bs4 import BeautifulSoup
import json
import os
import pandas as pd
import re
from datetime import datetime

# 監視対象の設定
TARGETS = [
    {"name": "医学図書出版", "url": "https://igakutosho.co.jp/collections/book", "selector": "h3", "type": "html"},
    {"name": "メディカルレビュー社", "url": "https://med.m-review.co.jp/merebo/products/book", "selector": ".name", "type": "html"},
    {"name": "診断と治療社", "url": "https://www.shindan.co.jp/", "selector": "dt", "type": "html"},
    {"name": "南江堂", "url": "https://www.nankodo.co.jp/shinkan/list.aspx?div=d", "selector": "tr", "type": "html"},
    {"name": "医学書院", "url": "https://www.igaku-shoin.co.jp/", "selector": ".book-title, .title", "type": "html"},
    {"name": "金原出版(GL検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=02", "selector": "h4", "type": "html"},
    {"name": "金原出版(規約検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=01", "selector": "h4", "type": "html"},
    {"name": "金原出版(お知らせ)", "url": "https://www.kanehara-shuppan.co.jp/news/index.html?no=151", "selector": "dt, dd", "type": "html"},
    {"name": "金原出版(規約PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/ky_new.pdf", "type": "pdf_header"},
    {"name": "金原出版(GL PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/gl_new.pdf", "type": "pdf_header"}
]

KEYWORDS = ["ガイドライン", "規約", "指針", "診療手引き", "診療指針", "治療指針", "作成指針"]
HISTORY_FILE = "history.json"
REPORT_FILE = "update_report.csv"
HTML_FILE = "index.html"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def clean_title(text):
    """ISBNや価格、余計な情報を強力に除去する"""
    # ISBN-13 (978...) や ISBN-10 のパターンを除去
    text = re.sub(r'ISBN\s?[:：]?\s?(97[89][- ]?)?([0-9Xx][- ]?){9,13}', '', text)
    # 価格表示の除去
    text = re.sub(r'(定価|本体|税込|税別)[:：]?\s?[0-9,]+円?.*', '', text)
    # 余計な「編集)」や「発行)」などのカッコ書きを除去(ノイズになりやすいため)
    text = re.sub(r'(編集|発行|著者|訳)\)?[:：].*', '', text)
    # 改行と重複スペースを整理
    text = " ".join(text.split())
    return text.strip()

def check_site(target):
    found_items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(target["url"], headers=headers, timeout=25)
        response.raise_for_status()

        if target["type"] == "html":
            soup = BeautifulSoup(response.content, "html.parser")
            selector = target.get("selector", "li, tr, div")
            for element in soup.select(selector):
                text = element.get_text(separator=" ").strip()
                if any(kw in text for kw in KEYWORDS):
                    if 8 < len(text) < 500:
                        full_text = clean_title(text)
                        found_items.append({"title": full_text[:150]})
        elif target["type"] == "pdf_header":
            last_mod = response.headers.get("Last-Modified")
            if last_mod:
                found_items.append({"title": "【PDF更新】" + target["name"]})
    except Exception as e:
        print(f"Error checking {target['name']}: {e}")
    return found_items

def generate_html(df):
    """CSVから見やすいHTMLページを生成する"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ガイドライン新着状況</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-50 p-4 md:p-8">
        <div class="max-w-5xl mx-auto">
            <h1 class="text-2xl font-bold mb-4 text-blue-800">診療ガイドライン新着ダッシュボード</h1>
            <p class="text-gray-600 mb-8">最終確認日時: {now}</p>
            <div class="bg-white shadow rounded-lg overflow-hidden">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-100">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">状態</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">出版社</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">内容</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">検知日</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200">
    """
    for _, row in df.iterrows():
        status_cls = "bg-red-100 text-red-800" if row['ステータス'] == "★新着" else "bg-gray-100 text-gray-600"
        html_content += f"""
                        <tr>
                            <td class="px-6 py-4 whitespace-nowrap"><span class="px-2 py-1 rounded text-xs {status_cls}">{row['ステータス']}</span></td>
                            <td class="px-6 py-4 whitespace-nowrap font-medium text-gray-900">{row['出版社']}</td>
                            <td class="px-6 py-4 text-sm text-gray-700"><a href="{row['URL']}" target="_blank" class="hover:underline text-blue-600">{row['タイトル内容']}</a></td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{row['検知日']}</td>
                        </tr>
        """
    html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    history = load_history()
    new_discoveries = []
    today = datetime.now().strftime("%Y-%m-%d")
    
    for target in TARGETS:
        site_name = target["name"]
        items = check_site(target)
        if site_name not in history: history[site_name] = []
        for item in items:
            title = item["title"]
            if title not in history[site_name]:
                new_discoveries.append({
                    "ステータス": "★新着", "出版社": site_name, "タイトル内容": title,
                    "URL": target["url"], "検知日": today
                })
                history[site_name].append(title)
    
    save_history(history)
    
    # データの統合とレポート保存
    if os.path.exists(REPORT_FILE):
        old_df = pd.read_csv(REPORT_FILE)
        if "ステータス" in old_df.columns: old_df["ステータス"] = "既知"
        df = pd.concat([pd.DataFrame(new_discoveries), old_df], ignore_index=True)
    else:
        df = pd.DataFrame(new_discoveries)
    
    if not df.empty:
        df.to_csv(REPORT_FILE, index=False, encoding="utf-8-sig")
        generate_html(df.head(100)) # 最新100件を表示
    
if __name__ == "__main__":
    main()

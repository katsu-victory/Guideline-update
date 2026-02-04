import requests
from bs4 import BeautifulSoup
import json
import os
import pandas as pd
import re
from datetime import datetime

# 監視対象の設定（セレクタを広めに設定し直し、漏れを防ぐ）
TARGETS = [
    {"name": "医学図書出版", "url": "https://igakutosho.co.jp/collections/book", "selector": "div.grid-view-item, .product-card", "type": "html"},
    {"name": "メディカルレビュー社", "url": "https://med.m-review.co.jp/merebo/products/book", "selector": ".product_list_item, li", "type": "html"},
    {"name": "診断と治療社", "url": "https://www.shindan.co.jp/", "selector": "dl, dt, li", "type": "html"},
    {"name": "南江堂", "url": "https://www.nankodo.co.jp/shinkan/list.aspx?div=d", "selector": "tr, div.shinkan-item", "type": "html"},
    {"name": "医学書院", "url": "https://www.igaku-shoin.co.jp/", "selector": "div.book-item, li", "type": "html"},
    {"name": "金原出版(GL検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=02", "selector": "div.book_list_item, tr, li", "type": "html"},
    {"name": "金原出版(規約検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=01", "selector": "div.book_list_item, tr, li", "type": "html"},
    {"name": "金原出版(お知らせ)", "url": "https://www.kanehara-shuppan.co.jp/news/index.html?no=151", "selector": "dl > *, li", "type": "html"},
    {"name": "金原出版(規約PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/ky_new.pdf", "type": "pdf_header"},
    {"name": "金原出版(GL PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/gl_new.pdf", "type": "pdf_header"}
]

# キーワード設定
KEYWORDS = ["ガイドライン", "規約", "指針", "診療手引き", "診療指針", "治療指針", "作成指針"]
# 日付抽出用（西暦4桁 + 区切り + 月(+日)）
DATE_PATTERN = r'(\d{4}[年/.\s]\d{1,2}[月/.\s](?:\d{1,2}日?)?)'
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

def extract_date(text):
    """テキスト内から日付を抽出。見つからなければタイトル内の日付を探す。"""
    match = re.search(DATE_PATTERN, text)
    if match:
        return match.group(1).strip()
    return "-"

def clean_title(text):
    """ノイズを除去するが、日付抽出の邪魔をしないように調整"""
    # ISBN
    text = re.sub(r'ISBN\s?[:：]?\s?(97[89][- ]?)?([0-9Xx][- ]?){9,13}', '', text)
    # 価格
    text = re.sub(r'(定価|本体|税込|税別)[:：]?\s?[0-9,]+円?.*', '', text)
    # 重複する空白や改行
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
            # 指定セレクタを順に試す
            selectors = target.get("selector", "li, tr, div").split(",")
            for sel in selectors:
                for element in soup.select(sel.strip()):
                    text = element.get_text(separator=" ").strip()
                    if any(kw in text for kw in KEYWORDS):
                        # 極端に長い/短いものは除外（フッターやメニュー対策）
                        if 10 < len(text) < 600:
                            pub_date = extract_date(text)
                            # タイトルからはノイズを削るが、2024年版などの重要な文字列は残す
                            cleaned = clean_title(text)
                            # 長すぎる場合は重要そうな前半部分を優先
                            title_part = cleaned[:200]
                            found_items.append({
                                "title": title_part,
                                "pub_date": pub_date
                            })
            
            # 1件も取れなかった場合のフォールバック（広域検索）
            if not found_items:
                for tag in soup.find_all(["a", "h3", "h4"]):
                    t = tag.get_text().strip()
                    if any(kw in t for kw in KEYWORDS) and len(t) > 8:
                        found_items.append({"title": clean_title(t), "pub_date": extract_date(t)})

        elif target["type"] == "pdf_header":
            last_mod = response.headers.get("Last-Modified")
            found_items.append({
                "title": "【PDF更新】" + target["name"],
                "pub_date": last_mod if last_mod else "-"
            })
    except Exception as e:
        print(f"Error checking {target['name']}: {e}")
    return found_items

def generate_html(df):
    """HTMLダッシュボード生成。発刊日を表示。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 表示用データの整理
    display_data = []
    for _, row in df.iterrows():
        # タイトル列の解決
        title = "-"
        for col in ["タイトル内容", "内容", "GL名"]:
            if col in row and pd.notna(row[col]) and row[col] != "-":
                title = str(row[col])
                break
        
        # 日付の補完：タイトル内に日付があればそれを使う
        p_date = str(row.get("発刊日", "-"))
        if p_date == "-" or p_date == "日付不明":
            p_date = extract_date(title)

        display_data.append({
            "status": str(row.get("ステータス", "既知")),
            "publisher": str(row.get("出版社", "-")),
            "pub_date": p_date,
            "title": title,
            "url": str(row.get("URL", "#")),
            "detect_date": str(row.get("検知日", "-"))
        })

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ガイドライン新着状況</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-50 p-4 md:p-8 font-sans text-gray-900">
        <div class="max-w-7xl mx-auto">
            <header class="mb-10">
                <h1 class="text-3xl font-extrabold text-blue-900">診療ガイドライン新着監視</h1>
                <p class="text-gray-500 mt-2">最終巡回: {now}</p>
            </header>
            
            <div class="bg-white shadow-xl rounded-2xl overflow-hidden border border-gray-200">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">状態</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">出版社</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">発刊日</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">タイトル・内容</th>
                            <th class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider whitespace-nowrap">検知日</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-100">
    """
    for row in display_data:
        is_new = "新着" in row['status']
        status_cls = "bg-red-500 text-white" if is_new else "bg-gray-100 text-gray-500"
        row_cls = "bg-red-50/30" if is_new else ""
        
        html_content += f"""
                        <tr class="hover:bg-blue-50 transition-colors {row_cls}">
                            <td class="px-6 py-4 whitespace-nowrap"><span class="px-3 py-1 rounded-full text-xs font-bold {status_cls}">{row['status']}</span></td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-bold text-gray-800">{row['publisher']}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-blue-700 font-bold">{row['pub_date']}</td>
                            <td class="px-6 py-4 text-sm leading-relaxed">
                                <a href="{row['url']}" target="_blank" class="text-blue-600 hover:text-blue-800 font-medium">
                                    {row['title']}
                                </a>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-400">{row['detect_date']}</td>
                        </tr>
        """
    html_content += """
                    </tbody>
                </table>
            </div>
            <footer class="mt-8 text-center text-gray-400 text-sm">
                ※タイトルをクリックすると各サイトの該当ページが開きます。
            </footer>
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
    
    # クローリング
    for target in TARGETS:
        site_name = target["name"]
        print(f"Checking {site_name}...")
        items = check_site(target)
        if site_name not in history: history[site_name] = []
        
        for item in items:
            title = item["title"]
            pub_date = item.get("pub_date", "-")
            # 履歴にないかチェック
            if title not in history[site_name]:
                new_discoveries.append({
                    "ステータス": "★新着", "出版社": site_name, "発刊日": pub_date,
                    "タイトル内容": title, "URL": target["url"], "検知日": today
                })
                history[site_name].append(title)
    
    save_history(history)
    
    # 既存レポートとの統合
    if os.path.exists(REPORT_FILE):
        try:
            old_df = pd.read_csv(REPORT_FILE)
            # 列名の読み替え
            rename_map = {"内容": "タイトル内容", "GL名": "タイトル内容", "確認日時": "検知日"}
            old_df = old_df.rename(columns=rename_map)
            
            if "ステータス" in old_df.columns:
                old_df["ステータス"] = "既知"
            
            # 必要な列を確保
            valid_cols = ["ステータス", "出版社", "発刊日", "タイトル内容", "URL", "検知日"]
            for col in valid_cols:
                if col not in old_df.columns:
                    old_df[col] = "-"
            
            old_df = old_df[valid_cols]
            
            new_df = pd.DataFrame(new_discoveries)
            if not new_df.empty:
                df = pd.concat([new_df, old_df], ignore_index=True)
            else:
                df = old_df
        except:
            df = pd.DataFrame(new_discoveries)
    else:
        df = pd.DataFrame(new_discoveries)
    
    if not df.empty:
        # 重複削除
        df = df.drop_duplicates(subset=["タイトル内容"], keep="first")
        df.to_csv(REPORT_FILE, index=False, encoding="utf-8-sig")
        generate_html(df.head(150)) # 表示件数を少し増量
    
if __name__ == "__main__":
    main()

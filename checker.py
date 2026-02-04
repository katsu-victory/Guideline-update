import requests
from bs4 import BeautifulSoup
import json
import os
import pandas as pd
from datetime import datetime

# 監視対象の設定
TARGETS = [
    {"name": "医学図書出版", "url": "https://igakutosho.co.jp/collections/book", "type": "html"},
    {"name": "メディカルレビュー社", "url": "https://med.m-review.co.jp/merebo/products/book", "type": "html"},
    {"name": "診断と治療社", "url": "https://www.shindan.co.jp/", "type": "html"},
    {"name": "南江堂", "url": "https://www.nankodo.co.jp/shinkan/list.aspx?div=d", "type": "html"},
    {"name": "医学書院", "url": "https://www.igaku-shoin.co.jp/", "type": "html"},
    {"name": "金原出版(GL検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=02", "type": "html"},
    {"name": "金原出版(規約検索)", "url": "https://www.kanehara-shuppan.co.jp/books/search_list.html?d=08&c=01", "type": "html"},
    {"name": "金原出版(お知らせ)", "url": "https://www.kanehara-shuppan.co.jp/news/index.html?no=151", "type": "html"},
    {"name": "金原出版(規約PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/ky_new.pdf", "type": "pdf_header"},
    {"name": "金原出版(GL PDF)", "url": "https://www.kanehara-shuppan.co.jp/_data/books/gl_new.pdf", "type": "pdf_header"}
]

KEYWORDS = ["ガイドライン", "規約", "指針", "診療手引き"]
HISTORY_FILE = "history.json"
REPORT_FILE = "update_report.csv"

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

def check_site(target):
    found_items = []
    try:
        # User-Agentを設定してブロックを防ぐ
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(target["url"], headers=headers, timeout=20)
        response.raise_for_status()

        if target["type"] == "html":
            soup = BeautifulSoup(response.content, "html.parser")
            # aタグやhタグなどからテキストを抽出
            tags = soup.find_all(["a", "h2", "h3", "div", "p"])
            for tag in tags:
                text = tag.get_text().strip()
                # キーワードが含まれているか、かつ適切な長さか
                if any(kw in text for kw in KEYWORDS):
                    if 5 < len(text) < 150:
                        # 改行などを整理
                        clean_text = " ".join(text.split())
                        found_items.append(clean_text)
        
        elif target["type"] == "pdf_header":
            # PDFは内容の代わりに更新情報を取得
            last_mod = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
            if last_mod or etag:
                found_items.append(f"PDF更新検知: {last_mod or etag}")

    except Exception as e:
        print(f"Error checking {target['name']}: {e}")
    
    return list(set(found_items))

def main():
    history = load_history()
    new_discoveries = []
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"--- 巡回開始: {today} ---")
    
    for target in TARGETS:
        site_name = target["name"]
        print(f"Checking {site_name}...")
        items = check_site(target)
        
        if site_name not in history:
            history[site_name] = []
            
        for item in items:
            if item not in history[site_name]:
                new_discoveries.append({
                    "出版社": site_name,
                    "内容": item,
                    "URL": target["url"],
                    "検知日": today
                })
                history[site_name].append(item)
    
    save_history(history)
    
    # レポートの作成・追記
    if new_discoveries:
        new_df = pd.DataFrame(new_discoveries)
        
        # 以前の古い形式のファイルをリセットして新しく作り直す（初回のみ）
        # もし既に正しいヘッダーのファイルがあれば追記する
        if os.path.exists(REPORT_FILE):
            try:
                old_df = pd.read_csv(REPORT_FILE)
                # ヘッダーが旧形式（IDが含まれるなど）ならリセット
                if "ID" in old_df.columns or "CSV記載日" in old_df.columns:
                    combined_df = new_df
                else:
                    combined_df = pd.concat([old_df, new_df], ignore_index=True)
            except:
                combined_df = new_df
        else:
            combined_df = new_df
            
        combined_df.to_csv(REPORT_FILE, index=False, encoding="utf-8-sig")
        print(f"\n{len(new_discoveries)} 件の新しいガイドライン/規約が見つかりました。")
    else:
        print("\n新しい情報は検知されませんでした。")

if __name__ == "__main__":
    main()

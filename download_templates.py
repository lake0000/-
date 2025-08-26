#!/usr/bin/env python3
# download_templates.py
# 批量从 htfsfwb.samr.gov.cn 下载 Word/PDF 模板（根据 detail URL 中的 id）

import os, csv, argparse, time, urllib.parse, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from tqdm import tqdm

BASE = "https://htsfwb.samr.gov.cn"
DOWNLOAD_API = BASE + "/api/File/DownTemplate?id={id}&type={type}"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def parse_cookie_string(cookie_str):
    cookies = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k,v = part.strip().split("=",1)
            cookies[k]=v
    return cookies

def safe_filename(s):
    # 简单安全文件名
    return "".join([c if c.isalnum() or c in " ._-()" else "_" for c in s])[:180]

def extract_id_from_url(url):
    try:
        u = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(u.query)
        if "id" in qs and qs["id"]:
            return qs["id"][0]
        # 也可能 detail_url 本身就是 /View?id=...
        # 如果 URL 是完整 path like '/View?id=...' handle
        m = urllib.parse.parse_qs(url)
    except:
        return None
    return None

def download_one(session, entry, outdir, types, timeout=60, retries=2):
    """
    entry: dict with keys: section,title,detail_url,... (来自 CSV)
    types: list of 'pdf'/'word' to attempt
    """
    detail_url = entry.get("detail_url") or entry.get("file_url") or entry.get("detail")
    title = entry.get("title") or entry.get("name") or "item"
    section = entry.get("section") or "unknown"
    if not detail_url:
        return False, "no_detail_url"

    # 取 id（从 detail_url 的 query 中）
    uid = None
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(detail_url).query)
        uid = qs.get("id", [None])[0]
    except:
        uid = None
    if not uid:
        # 有些 CSV 里 detail_url 可能是直接 "https://htsfwb.../View?id=..."
        # 尝试用 string find
        if "id=" in detail_url:
            uid = detail_url.split("id=")[-1].split("&")[0]
    if not uid:
        return False, "no_id"

    saved = []
    for t in types:
        typ_num = 2 if t.lower()=="pdf" else 1
        url = DOWNLOAD_API.format(id=uid, type=typ_num)
        # referer 使用详情页更可信
        headers = COMMON_HEADERS.copy()
        headers["Referer"] = detail_url
        ok = False
        last_err = None
        for attempt in range(retries+1):
            try:
                with session.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as r:
                    # 如果返回是 HTML（content-type text/html），很可能是错误页或需要登录/验证
                    ctype = r.headers.get("Content-Type","").lower()
                    if r.status_code != 200:
                        last_err = f"status {r.status_code}"
                        # 保存调试页面
                        debug_dir = os.path.join(outdir,"debug_html")
                        os.makedirs(debug_dir, exist_ok=True)
                        try:
                            text = r.text
                            with open(os.path.join(debug_dir, f"{uid}_{typ_num}_status{r.status_code}.html"), "w", encoding="utf-8") as fh:
                                fh.write(text)
                        except Exception:
                            pass
                        time.sleep(1 + attempt*1.5)
                        continue
                    # 若 content-type 是 pdf 或 word 或 octet-stream 则保存
                    ext = None
                    if "pdf" in ctype:
                        ext = ".pdf"
                    elif "officedocument.wordprocessingml.document" in ctype or "word" in ctype or "msword" in ctype:
                        # docx / doc
                        if "officedocument.wordprocessingml.document" in ctype:
                            ext = ".docx"
                        else:
                            ext = ".doc"
                    else:
                        # 可能没有设置 content-type，但 response header 有 Content-Disposition
                        cd = r.headers.get("Content-Disposition","")
                        if "filename=" in cd:
                            fname = cd.split("filename=")[-1].strip(' "')
                            ext = os.path.splitext(fname)[1] or ".bin"
                        else:
                            # 如果 body 看起来是 PDF（%%PDF 标头），则当作 pdf
                            head = r.raw.read(8)
                            r.raw.seek(0)
                            if head.startswith(b'%PDF'):
                                ext = ".pdf"
                    if not ext:
                        # 保存为调试 html，表示下载失败或被拦截
                        debug_dir = os.path.join(outdir,"debug_html")
                        os.makedirs(debug_dir, exist_ok=True)
                        body = r.content
                        fname_debug = os.path.join(debug_dir, f"{uid}_{typ_num}_notbinary.html")
                        try:
                            with open(fname_debug, "wb") as fh:
                                fh.write(body)
                        except Exception:
                            pass
                        last_err = "not_binary_content"
                        time.sleep(1 + attempt*1.5)
                        continue

                    # 构造输出文件名
                    safe_title = safe_filename(title)
                    save_dir = os.path.join(outdir, section)
                    os.makedirs(save_dir, exist_ok=True)
                    filename = f"{safe_title}{ext}"
                    outpath = os.path.join(save_dir, filename)
                    # 若同名文件存在，附加 uid
                    if os.path.exists(outpath):
                        base, e = os.path.splitext(filename)
                        filename = f"{base}_{uid}{e}"
                        outpath = os.path.join(save_dir, filename)

                    # 保存二进制
                    with open(outpath + ".part", "wb") as fh:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                fh.write(chunk)
                    os.replace(outpath + ".part", outpath)
                    saved.append(outpath)
                    ok = True
                    break
            except Exception as e:
                last_err = str(e)
                time.sleep(1 + attempt*1.5)
                continue
        if not ok:
            # 记录失败
            return False, f"fail_{t}:{last_err}"
    return True, saved

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, help="输入 CSV 文件，包含 detail_url/title/section 等列")
    ap.add_argument("--out", "-o", default="downloads", help="输出目录")
    ap.add_argument("--types", default="pdf", help="下载类型：pdf,word 或 pdf,word （逗号分隔，顺序表示优先级）")
    ap.add_argument("--cookie", default="", help="浏览器里复制的 cookie 字符串，例如: '__jsluid_s=...; samr=isopen'")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    types = [t.strip().lower() for t in args.types.split(",") if t.strip()]
    if not types:
        types = ["pdf"]

    # 读取 CSV
    rows = []
    with open(args.input, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)

    print("总行数:", len(rows))
    session = requests.Session()
    session.headers.update(COMMON_HEADERS)
    if args.cookie:
        cookies = parse_cookie_string(args.cookie)
        session.cookies.update(cookies)

    outdir = os.path.abspath(args.out)
    os.makedirs(outdir, exist_ok=True)

    results = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {}
        for entry in rows:
            fut = ex.submit(download_one, session, entry, outdir, types)
            futures[fut] = entry
        for fut in tqdm(as_completed(futures), total=len(futures), desc="下载任务"):
            entry = futures[fut]
            try:
                ok, info = fut.result()
            except Exception as e:
                ok = False
                info = str(e)
            with lock:
                results.append((entry, ok, info))

    # 写入结果 CSV
    outcsv = os.path.join(outdir, "download_results.csv")
    with open(outcsv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["title","detail_url","section","ok","info"])
        for entry, ok, info in results:
            writer.writerow([entry.get("title"), entry.get("detail_url"), entry.get("section"), ok, info])
    print("完成，结果保存：", outcsv)

if __name__ == "__main__":
    main()

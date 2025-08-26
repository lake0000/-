# collect_all_by_clicks.py
# 用法:
#   python E:\collect_all_by_clicks.py --section national
#   python E:\collect_all_by_clicks.py --section local
# 依赖: selenium webdriver-manager beautifulsoup4 lxml requests
# 安装:
#   conda activate pachong-py311
#   python -m pip install selenium webdriver-manager beautifulsoup4 lxml requests

import time, csv, argparse, os, re, urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

BASE = "https://htsfwb.samr.gov.cn"
START_PATH = {"national": "/National", "local": "/Local"}

def make_driver(headless=False, proxy=None):
    opts = Options()
    if headless:
        try:
            opts.add_argument("--headless=new")
        except:
            opts.add_argument("--headless")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    if proxy:
        opts.add_argument(f"--proxy-server={proxy}")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except:
        pass
    return driver

def extract_items_from_html(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.find_all("a", href=True):
        href = a['href']
        if "/View?id=" in href:
            url = urllib.parse.urljoin(BASE, href)
            title = a.get_text(" ", strip=True)
            items.append((title, url))
    return items

def find_pagination_element(driver):
    # 多种选择器尝试
    selectors = [
        ".samr-pagination", ".pagination", ".paging", ".pager", ".pagerbox", ".samr-home-list-box .samr-pagination"
    ]
    for s in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, s)
            return el
        except:
            continue
    # 最后的尝试：按 page number a 元素集合
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "a")
        cand = []
        for e in els:
            txt = (e.text or "").strip()
            if re.match(r'^\d+$', txt):
                cand.append(e)
        if cand:
            return cand[0].find_element(By.XPATH, "..")  # parent as approximation
    except:
        pass
    return None

def click_page_and_collect(driver, page_num):
    # 找到页面上 data-page 或 内文为数字 的链接并点击
    try:
        # 优先用 data-page 属性匹配
        el = driver.find_element(By.CSS_SELECTOR, f'a[data-page="{page_num}"]')
    except:
        el = None
    if not el:
        # 按显示文本匹配（数字）
        elems = driver.find_elements(By.XPATH, f'//a[normalize-space(text())="{page_num}"]')
        el = elems[0] if elems else None
    if not el:
        # 尝试 next/prev pattern 里查找数字链接
        try:
            container = find_pagination_element(driver)
            if container:
                anchors = container.find_elements(By.TAG_NAME, "a")
                for a in anchors:
                    txt = (a.text or "").strip()
                    if txt == str(page_num):
                        el = a
                        break
        except:
            el = None
    if not el:
        return False, "找不到页码元素"

    # 点击并等待列表更新（通过等待某个 item 出现或 page source 变更）
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        time.sleep(0.2)
        el.click()
    except Exception as e:
        try:
            href = el.get_attribute("href")
            if href:
                driver.get(href)
            else:
                return False, f"点击或跳转失败: {e}"
        except Exception as e2:
            return False, f"点击失败: {e2}"

    # 等待列表区域加载：这里等待有 item 节点出现
    try:
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".samr-home-list .item, .item-box .item, .samr-home-list .item-box .item")))
    except:
        # 如果等待失败也继续抓取（可能页面结构不同）
        pass
    time.sleep(0.6)  # 轻微等待渲染完成
    html = driver.page_source
    items = extract_items_from_html(html)
    return True, items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", choices=["national","local"], required=True)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-pages", type=int, default=999)
    ap.add_argument("--proxy", default="")
    args = ap.parse_args()

    start_url = BASE + START_PATH[args.section]
    driver = make_driver(headless=args.headless, proxy=args.proxy or None)
    try:
        driver.get(start_url)
        time.sleep(1.0)
        # 初始页先抓一次
        all_items = {}
        html0 = driver.page_source
        items0 = extract_items_from_html(html0)
        for t,u in items0:
            all_items[u] = {"section": args.section, "title": t, "detail_url": u}
        print(f"[page 1] 新增 {len(items0)} 条 (累计 {len(all_items)})")

        # 找分页元素，尝试读取页码总数（如果页码显示）
        total_pages = None
        try:
            pag = find_pagination_element(driver)
            if pag:
                # 尝试获取所有页码数字
                anchors = pag.find_elements(By.TAG_NAME, "a")
                nums = []
                for a in anchors:
                    txt = (a.text or "").strip()
                    if txt.isdigit():
                        nums.append(int(txt))
                if nums:
                    total_pages = max(nums)
        except Exception:
            total_pages = None

        if total_pages is None:
            print("未能直接读取总页数，脚本会按 --max-pages 限制进行尝试")

        max_try = total_pages if (total_pages and total_pages>1) else args.max_pages

        # 从 page 2 开始循环点击
        current = 2
        while current <= max_try:
            print("尝试翻到第", current, "页")
            ok, res = click_page_and_collect(driver, current)
            if not ok:
                print("  翻页失败或找不到页码：", res)
                # 如果找不到 page element，尝试通过 "下一页" 按钮点击
                try:
                    nxt = driver.find_element(By.CSS_SELECTOR, "a.next, .next, a[aria-label='Next']")
                    driver.execute_script("arguments[0].scrollIntoView(true);", nxt)
                    time.sleep(0.2)
                    nxt.click()
                    time.sleep(1.0)
                    html = driver.page_source
                    items = extract_items_from_html(html)
                except Exception as e:
                    print("  尝试点击 next 也失败，停止翻页:", e)
                    break
            else:
                items = res

            # 统计新增
            new_count = 0
            for t,u in items:
                if u not in all_items:
                    all_items[u] = {"section": args.section, "title": t, "detail_url": u}
                    new_count += 1
            print(f"  页面提取 {len(items)} 条，新增 {new_count} 条（累计 {len(all_items)}）")

            # 如果页码超出分页显示范围（例如分页只有 5 页），当 new_count==0 两三次后停止
            # 简单策略：若连续三页无新增则停止
            # 这里使用一个小状态变量
            # （实现：若 new_count==0 增加连续无新增计数）
            # 我们在循环外维护该计数
            if 'consec_no_new' not in locals():
                consec_no_new = 0
            if new_count == 0:
                consec_no_new += 1
            else:
                consec_no_new = 0
            if consec_no_new >= 3:
                print("连续多页无新增，认为已到末页，停止")
                break

            current += 1
            time.sleep(0.5)

        # 写 CSV
        out = f"outputs_all_{args.section}_by_clicks.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["section","title","detail_url"])
            writer.writeheader()
            for v in all_items.values():
                writer.writerow(v)
        print("保存 ->", out, " 共", len(all_items))
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()

# -
合同示范文本库爬虫代码
网站：https://htsfwb.samr.gov.cn/
#collect文件用于获取ULR 
#download文件用于通过ULR下载PDF以及WORD版本的合同
#collect_all_by_clicks.py用法:
#   python collect_all_by_clicks.py --section national
#   python collect_all_by_clicks.py --section local
# 依赖: selenium webdriver-manager beautifulsoup4 lxml requests
# 安装:
#   conda activate pachong-py311
#   python -m pip install selenium webdriver-manager beautifulsoup4 lxml requests

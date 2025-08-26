## 合同示范文本库爬虫代码
- **网站**：[https://htsfwb.samr.gov.cn/](https://htsfwb.samr.gov.cn/)

### 文件功能
- **`collect` 文件**：用于获取URL。
- **`download` 文件**：通过URL下载PDF以及WORD版本的合同。

### 脚本用法
- **`collect_all_by_clicks.py` 用法**：
  - `python collect_all_by_clicks.py --section national`
  - `python collect_all_by_clicks.py --section local`

### 依赖库
- **依赖**：
  - selenium
  - webdriver-manager
  - beautifulsoup4
  - lxml
  - requests

### 安装步骤
- **安装**：
  - `conda activate pachong-py311`
  - `python -m pip install selenium webdriver-manager beautifulsoup4 lxml requests`

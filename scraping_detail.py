from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from tqdm import tqdm

import time
import json

with open("products.json", "r",encoding="utf-8") as f:
    products = json.load(f)

options = Options()
options.add_argument("--headless")  # ไม่เปิด browser จริง
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
driver = webdriver.Chrome(options=options)

Count_success = 0
Count_error = 0
matched_products = list()

# for product in products:
for product in tqdm(products, desc="Scraping products", unit="item"):
    url = product['link']
    driver.get(url)
    time.sleep(3)  # รอให้ JS โหลดเสร็จ (อาจปรับเป็น WebDriverWait)

    try:
        desc = driver.find_element(By.CSS_SELECTOR, "div[data-testid='product-description-wrapper']")
        product['description'] = desc.text.strip()
        matched_products.append(product)
        Count_success += 1

    except:
        print("❌ ไม่เจอ description:", product["name"])
        Count_error += 1 

driver.quit()

with open("products_with_desc.json", "w",encoding="utf-8") as f:
    json.dump(matched_products, f, ensure_ascii=False, indent=2)

print("Matched link: {} links".format(Count_success))
print("Unmatched link: {} links".format(Count_error))
print("Saved new file: products_with_desc.json")
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def load_all_products(driver):
    while True:
        try:
            # รอปุ่ม "ดูเพิ่มเติม" โผล่ (3 วินาที)
            show_more_btn = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-cy='Show-More']"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", show_more_btn)
            time.sleep(0.5)

            # คลิกปุ่ม
            show_more_btn.click()
            print("✅ กด 'ดูเพิ่มเติม' แล้ว")

            # รอโหลดสินค้าใหม่
            time.sleep(2)

        except (TimeoutException, NoSuchElementException):
            print("❌ ไม่เจอปุ่ม 'ดูเพิ่มเติม' แล้ว → โหลดสินค้าครบแล้ว")
            break

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://www.decathlon.co.th/c/%E0%B8%9F%E0%B8%B4%E0%B8%95%E0%B9%80%E0%B8%99%E0%B8%AA/%E0%B8%AD%E0%B8%B8%E0%B8%9B%E0%B8%81%E0%B8%A3%E0%B8%93%E0%B9%8C%E0%B9%80%E0%B8%A7%E0%B8%97%E0%B9%80%E0%B8%97%E0%B8%A3%E0%B8%99%E0%B8%99%E0%B8%B4%E0%B9%88%E0%B8%87/%E0%B8%9A%E0%B8%AD%E0%B8%94%E0%B8%B5%E0%B9%89%E0%B9%80%E0%B8%A7%E0%B8%97.html?color=%23000000#")

wait = WebDriverWait(driver, 15)

load_all_products(driver)

# รอให้การ์ดสินค้าปรากฏ
cards = wait.until(EC.presence_of_all_elements_located(
    (By.CSS_SELECTOR, "div[data-testid='productHit-tilesbox-gridcell']"))
)

print(f"เจอสินค้าทั้งหมด: {len(cards)} ชิ้น")

for card in cards[:6]:
    try:
        # เลื่อนเข้ากลางจอเพื่อกระตุ้น lazy rendering
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
        time.sleep(0.2)

        # LINK – ใช้ selector แบบ fallback: มีทั้ง data-cy และ href ที่ขึ้นต้นด้วย /p/
        try:
            link_el = WebDriverWait(card, 5).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "a[data-cy='productTitle'], a[href^='/p/']")))
            link = link_el.get_attribute("href")
            # ถ้าลิงก์เป็น path ให้แปลงเป็นเต็ม
            if link and link.startswith("/"):
                link = "https://www.decathlon.co.th" + link
        except:
            link = None

        # ชื่อสินค้า
        try:
            name = card.find_element(By.CSS_SELECTOR, "div[title]").get_attribute("title")
        except:
            name = ""

        # PRICE 
        try:
            price = card.find_element(By.CSS_SELECTOR, "span[data-cy='item-current-price'], span.vp-price-amount").text
        except:
            price = ""

        # IMAGE
        try:
            img = card.find_element(By.CSS_SELECTOR, "img").get_attribute("src")
        except:
            img = ""

        if not name and not link:
            continue

        print("ชื่อสินค้า:", name)
        print("ราคา:", price)
        print("ลิงก์รายละเอียด:", link)
        print("ลิงค์รูปภาพ:", img)
        print("-" * 60)

    except Exception as e:
        print("Error on card:", e)

driver.quit()
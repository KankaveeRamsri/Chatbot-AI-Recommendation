import time
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException

URL = "https://www.decathlon.co.th/c/%E0%B8%9F%E0%B8%B4%E0%B8%95%E0%B9%80%E0%B8%99%E0%B8%AA/%E0%B8%AD%E0%B8%B8%E0%B8%9B%E0%B8%81%E0%B8%A3%E0%B8%93%E0%B9%8C%E0%B9%80%E0%B8%A7%E0%B8%97%E0%B9%80%E0%B8%97%E0%B8%A3%E0%B8%99%E0%B8%99%E0%B8%B4%E0%B9%88%E0%B8%87/%E0%B8%9A%E0%B8%AD%E0%B8%94%E0%B8%B5%E0%B9%89%E0%B9%80%E0%B8%A7%E0%B8%97.html?color=%23000000#"

SHOW_MORE_SEL = "button[data-cy='Show-More']"
CARD_SEL = "div[data-testid='productHit-tilesbox-gridcell']"
LINK_SEL = "a[data-cy='productTitle'], a[href^='/p/']"
NAME_SEL = "div[title]"
PRICE_SEL = "span[data-cy='item-current-price'], span.vp-price-amount"
IMG_SEL = "img"

def get_product_count(driver):
    return len(driver.find_elements(By.CSS_SELECTOR, CARD_SEL))

def click_show_more_until_done(driver, wait, max_no_growth_rounds=3):
    """กดปุ่ม 'ดูเพิ่มเติม' ไปเรื่อย ๆ จนไม่มีเพิ่มแล้วหรือปุ่มหาย พร้อมตรวจว่าจำนวนสินค้าเพิ่มจริง"""
    no_growth_rounds = 0
    while True:
        # หา count ปัจจุบัน
        before = get_product_count(driver)

        # หาและเช็คปุ่ม
        try:
            btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SHOW_MORE_SEL)))
        except TimeoutException:
            print("❌ ไม่เจอปุ่ม 'ดูเพิ่มเติม' แล้ว → น่าจะครบ")
            break

        # ถ้ามีให้คลิก
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.2)

            # ลองคลิกปกติก่อน ถ้าโดน overlay บัง ค่อย JS click
            try:
                wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SHOW_MORE_SEL)))
                btn.click()
            except (ElementClickInterceptedException, TimeoutException):
                driver.execute_script("arguments[0].click();", btn)

            print("✅ คลิก 'ดูเพิ่มเติม'")
        except StaleElementReferenceException:
            # DOM เปลี่ยนทันที ระหว่างกำลังคลิก — วนรอบใหม่
            print("ℹ️ ปุ่ม stale ลองใหม่")
            continue

        # รอให้จำนวนสินค้าเพิ่มขึ้น หรือหมดเวลา
        try:
            wait.until(lambda d: get_product_count(d) > before)
            after = get_product_count(driver)
            print(f"➡️ จำนวนสินค้าเพิ่ม: {before} → {after}")
            no_growth_rounds = 0
        except TimeoutException:
            # ถ้าไม่มีการเพิ่มต่อเนื่องหลายรอบ ให้จบ
            no_growth_rounds += 1
            print(f"⚠️ ไม่มีสินค้าขึ้นเพิ่มในรอบนี้ (รอบที่ {no_growth_rounds})")
            if no_growth_rounds >= max_no_growth_rounds:
                print("❌ สินค้าไม่เพิ่มต่อเนื่องหลายรอบ → หยุดคลิก")
                break

        # กัน rate-limit / animation
        time.sleep(0.5)

def extract_cards(driver):
    cards = driver.find_elements(By.CSS_SELECTOR, CARD_SEL)
    print(f"เจอสินค้าทั้งหมด: {len(cards)} ชิ้น")

    data = []

    # (ตัวเลือก) ถ้าต้องการเลื่อนจาก 'ล่างขึ้นบน' เพื่อกระตุ้น lazy-load รูปภาพ เปิด block นี้:
    # for card in cards[::-1]:
    #     driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
    #     time.sleep(0.05)

    # ไม่เลื่อนก็ได้ อ่านจาก DOM เลย
    for idx, card in enumerate(cards, 1):
        try:
            # LINK
            link = ""
            try:
                link_el = card.find_element(By.CSS_SELECTOR, LINK_SEL)
                link = link_el.get_attribute("href") or ""
                if link.startswith("/"):
                    link = "https://www.decathlon.co.th" + link
            except NoSuchElementException:
                pass

            # NAME
            name = ""
            try:
                name = card.find_element(By.CSS_SELECTOR, NAME_SEL).get_attribute("title") or ""
                if not name:
                    # fallback: ใช้ textContent
                    name = card.find_element(By.CSS_SELECTOR, NAME_SEL).text
            except NoSuchElementException:
                pass

            # PRICE
            price = ""
            try:
                price = card.find_element(By.CSS_SELECTOR, PRICE_SEL).text
            except NoSuchElementException:
                pass

            # IMAGE (พยายามอ่าน srcset ถ้ามี เพื่อได้รูปคม)
            img = ""
            try:
                img_el = card.find_element(By.CSS_SELECTOR, IMG_SEL)
                srcset = img_el.get_attribute("srcset")
                if srcset:
                    # เอา URL แรก (หรือจะเอาอันสุดท้ายที่ความละเอียดสูงสุดก็ได้)
                    first = srcset.split(",")[0].strip().split(" ")[0]
                    img = first
                else:
                    img = img_el.get_attribute("src") or ""
            except NoSuchElementException:
                pass

            if not name and not link:
                continue

            data.append({
                "name": name.strip(),
                "price": price.strip(),
                "link": link.strip(),
                "image": img.strip()
            })

        except Exception as e:
            print(f"Error on card #{idx}: {e}")

    return data

if __name__ == "__main__":
    # -------------------- MAIN --------------------
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")  # ถ้าจะรัน headless ให้เปิดบรรทัดนี้
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 15)

    driver.get(URL)

    # 1) คลิก 'ดูเพิ่มเติม' จนสุด + เช็คจำนวนสินค้าเพิ่มจริง
    click_show_more_until_done(driver, wait, max_no_growth_rounds=2)

    # 2) ดึงข้อมูลจากการ์ดทั้งหมดทีเดียว
    items = extract_cards(driver)

    # แสดงผลตัวอย่าง
    for it in items[:6]:
        print(it)

    print(f"\n✅ รวมทั้งหมด {len(items)} ชิ้น")

    # บันทึกเป็น JSON (utf-8, indent สวยงาม)
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("✅ บันทึกข้อมูลลง products.json เรียบร้อยแล้ว")

    driver.quit()

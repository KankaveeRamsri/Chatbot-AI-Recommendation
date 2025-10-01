import os
import random
import numpy as np
import faiss
from flask import Flask, request, abort
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, CarouselTemplate, CarouselColumn, URITemplateAction
)
from linebot.models import QuickReply, QuickReplyButton, MessageAction

app = Flask(__name__)

# -------- LINE Config --------
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "10cc7f532a62b2208f2bdeb03148705d")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "o0rmXIz8Xk1QDlHDkPbgLglKWg+qXjzOPnJt/21VmAXGBYuXkFQKlIyt71CpXQrAndBq5tsDAoj9BL+UUiVqkXHj7X1LeM7kRUfoBAgcbTzfo+3me0MPhMcFyF0Hpo1zdrRhbvhzSb5fsbVRURAeVgdB04t89/1O/w1cDnyilFU=")
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# -------- Neo4j Config --------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# -------- Embedding Model --------
model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

# -------- User Session --------
user_profiles = {}

# -------- Chain Questions (8 แต่สุ่ม 6) --------
all_questions = [
    {"id": "budget", "text": "คุณมีงบประมาณเท่าไหร่? (เช่น ไม่เกิน 500 / 500-1000 / 1000+)"},
    {"id": "place", "text": "คุณอยากใช้สินค้านี้ที่ไหน? (บ้าน, ฟิตเนส, สนามกีฬา)"},
    {"id": "size", "text": "คุณอยากได้สินค้าขนาดเท่าไหร่? (เล็ก, กลาง, ใหญ่)"},
    {"id": "feature", "text": "คุณต้องการคุณสมบัติเด่นแบบไหน? (ลดแรงกระแทก, ทำความสะอาดง่าย, ทนความร้อน)"},
    {"id": "material", "text": "คุณสนใจวัสดุอะไร? (EVA, ยาง, โฟม, ไม่ระบุ)"},
    {"id": "lifetime", "text": "คุณคาดหวังอายุการใช้งานกี่ปี? (1-2 ปี, 3-5 ปี, มากกว่า 5 ปี)"},
    {"id": "color", "text": "คุณอยากเลือกสีไหม? (เทา, ดำ, ไม่สำคัญ)"},
    {"id": "value", "text": "คุณอยากได้แบบคุ้มค่าราคา หรือคุณภาพสูงสุด? (คุ้มค่า / คุณภาพสูงสุด)"},
    {"id": "training_type", "text": "คุณเน้นการออกกำลังกายแบบไหน? (โยคะ/เวทเทรนนิ่ง/คาร์ดิโอ/ทั่วไป)"},
    {"id": "frequency", "text": "คุณออกกำลังกายบ่อยแค่ไหน? (1-2 ครั้ง/สัปดาห์, 3-5 ครั้ง, ทุกวัน)"},
    {"id": "storage", "text": "คุณต้องการเก็บสินค้าง่ายไหม? (พับเก็บได้, น้ำหนักเบา, ไม่สำคัญ)"},
    {"id": "safety", "text": "คุณกังวลเรื่องความปลอดภัยแบบไหน? (กันลื่น, กันกระแทก, ไม่สำคัญ)"},
    {"id": "brand", "text": "คุณสนใจแบรนด์เฉพาะหรือไม่? (Homefitt, Fittools, ไม่สำคัญ)"}
]

quick_map = {
            "budget": [
                QuickReplyButton(action=MessageAction(label="≤500", text="≤500")),
                QuickReplyButton(action=MessageAction(label="500-1000", text="500-1000")),
                QuickReplyButton(action=MessageAction(label="1000+", text="1000+"))
            ],
            "place": [
                QuickReplyButton(action=MessageAction(label="บ้าน", text="บ้าน")),
                QuickReplyButton(action=MessageAction(label="ฟิตเนส", text="ฟิตเนส")),
                QuickReplyButton(action=MessageAction(label="สนามกีฬา", text="สนามกีฬา"))
            ],
            "size": [
                QuickReplyButton(action=MessageAction(label="เล็ก", text="เล็ก")),
                QuickReplyButton(action=MessageAction(label="กลาง", text="กลาง")),
                QuickReplyButton(action=MessageAction(label="ใหญ่", text="ใหญ่"))
            ],
            "feature": [
                QuickReplyButton(action=MessageAction(label="ลดแรงกระแทก", text="ลดแรงกระแทก")),
                QuickReplyButton(action=MessageAction(label="ทำความสะอาดง่าย", text="ทำความสะอาดง่าย")),
                QuickReplyButton(action=MessageAction(label="ทนความร้อน", text="ทนความร้อน"))
            ],
            "material": [
                QuickReplyButton(action=MessageAction(label="EVA", text="EVA")),
                QuickReplyButton(action=MessageAction(label="ยาง", text="ยาง")),
                QuickReplyButton(action=MessageAction(label="โฟม", text="โฟม")),
                QuickReplyButton(action=MessageAction(label="ไม่ระบุ", text="ไม่ระบุ"))
            ],
            "lifetime": [
                QuickReplyButton(action=MessageAction(label="1-2 ปี", text="1-2 ปี")),
                QuickReplyButton(action=MessageAction(label="3-5 ปี", text="3-5 ปี")),
                QuickReplyButton(action=MessageAction(label="มากกว่า 5 ปี", text="มากกว่า 5 ปี"))
            ],
            "color": [
                QuickReplyButton(action=MessageAction(label="เทา", text="เทา")),
                QuickReplyButton(action=MessageAction(label="ดำ", text="ดำ")),
                QuickReplyButton(action=MessageAction(label="ไม่สำคัญ", text="ไม่สำคัญ"))
            ],
            "value": [
                QuickReplyButton(action=MessageAction(label="คุ้มค่า", text="คุ้มค่า")),
                QuickReplyButton(action=MessageAction(label="คุณภาพสูงสุด", text="คุณภาพสูงสุด"))
            ],
            "training_type": [
                QuickReplyButton(action=MessageAction(label="โยคะ", text="โยคะ")),
                QuickReplyButton(action=MessageAction(label="เวทเทรนนิ่ง", text="เวทเทรนนิ่ง")),
                QuickReplyButton(action=MessageAction(label="คาร์ดิโอ", text="คาร์ดิโอ")),
                QuickReplyButton(action=MessageAction(label="ทั่วไป", text="ทั่วไป"))
            ],
            "frequency": [
                QuickReplyButton(action=MessageAction(label="1-2 ครั้ง/สัปดาห์", text="1-2 ครั้ง/สัปดาห์")),
                QuickReplyButton(action=MessageAction(label="3-5 ครั้ง/สัปดาห์", text="3-5 ครั้ง/สัปดาห์")),
                QuickReplyButton(action=MessageAction(label="ทุกวัน", text="ทุกวัน"))
            ],
            "storage": [
                QuickReplyButton(action=MessageAction(label="พับเก็บได้", text="พับเก็บได้")),
                QuickReplyButton(action=MessageAction(label="น้ำหนักเบา", text="น้ำหนักเบา")),
                QuickReplyButton(action=MessageAction(label="ไม่สำคัญ", text="ไม่สำคัญ"))
            ],
            "safety": [
                QuickReplyButton(action=MessageAction(label="กันลื่น", text="กันลื่น")),
                QuickReplyButton(action=MessageAction(label="กันกระแทก", text="กันกระแทก")),
                QuickReplyButton(action=MessageAction(label="ไม่สำคัญ", text="ไม่สำคัญ"))
            ],
            "brand": [
                QuickReplyButton(action=MessageAction(label="Homefitt", text="Homefitt")),
                QuickReplyButton(action=MessageAction(label="Fittools", text="Fittools")),
                QuickReplyButton(action=MessageAction(label="ไม่สำคัญ", text="ไม่สำคัญ"))
            ]

        }

# ปุ่มพิเศษตอนเริ่มต้น (ไม่มี "แก้คำตอบก่อนหน้า")
extra_buttons_init = [
    QuickReplyButton(action=MessageAction(label="⏭ ข้ามคำถาม", text="ข้าม")),
    QuickReplyButton(action=MessageAction(label="🛒 สินค้าขายดี", text="สินค้าขายดี")),
]


# ปุ่มพิเศษที่อยากใส่เพิ่มทุกครั้ง
extra_buttons = [
    QuickReplyButton(action=MessageAction(label="🔄 แก้คำตอบก่อนหน้า", text="แก้คำตอบ")),
    QuickReplyButton(action=MessageAction(label="⏭ ข้ามคำถาม", text="ข้าม")),
    QuickReplyButton(action=MessageAction(label="🛒 สินค้าขายดี", text="สินค้าขายดี")),
]

# -------- Load Products from Neo4j --------
def load_products():
    with driver.session() as session:
        query = """
        MATCH (p:Product)-[:HAS_IMAGE]->(i:Image)
        RETURN p.name AS name,
               p.price AS price,
               p.url AS url,
               p.description AS description,
               i.url AS image_url
        """
        result = session.run(query)
        return [record.data() for record in result]

# -------- Build FAISS Index --------
def build_faiss_index(products):
    texts = [f"{p['name']} {p['description']} {p['price']}" for p in products]
    embeddings = model.encode(texts, normalize_embeddings=True)
    index = faiss.IndexFlatIP(embeddings.shape[1])  # cosine similarity
    index.add(embeddings)
    return index, embeddings

products = load_products()
index, embeddings = build_faiss_index(products)

# -------- FAISS Search --------
def search_products(query_text, top_k=5):
    query_vec = model.encode([query_text], normalize_embeddings=True)
    distances, indices = index.search(query_vec, top_k)
    return [products[i] for i in indices[0]]

# -------- Flask LINE Bot --------
@app.route("/", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# -------- Progress Bar --------
def get_progress_text(current, total):
    return f"({current}/{total}) ✅"

# -------- ฟังก์ชันส่งสินค้า --------
def send_product_carousel(reply_token, products):
    if not products:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="ไม่มีสินค้าตรงเงื่อนไขครับ"))
        return

    columns = []
    for p in products:
        col = CarouselColumn(
            title=p["name"][:40],
            text=f"ราคา: {p['price']}" if p["price"] else "N/A",
            thumbnail_image_url=p.get("image_url"),
            actions=[URITemplateAction(label="ดูรายละเอียด", uri=p["url"])]
        )
        columns.append(col)

    carousel = TemplateSendMessage(
        alt_text="สินค้าแนะนำ",
        template=CarouselTemplate(columns=columns)
    )
    line_bot_api.reply_message(reply_token, carousel)



@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    message = event.message.text.strip()

    # ---- init session ----
    if user_id not in user_profiles:
        selected = random.sample(all_questions, 7)
        user_profiles[user_id] = {
            "questions": selected,
            "answers": {},
            "current_q": 0,
            "finished": False
        }

        qid = selected[0]["id"]
        qtext = selected[0]["text"]
        progress = get_progress_text(1, len(selected))

        intro = (
        "สวัสดีครับ 🙌  \n"
        "ยินดีต้อนรับสู่ FitBot 🤖 ผู้ช่วยเลือกอุปกรณ์บอดี้เวทสำหรับคุณ  \n\n"
        "คุณอยากเริ่มออกกำลังกาย แต่ไม่แน่ใจว่าอุปกรณ์แบบไหนเหมาะกับตัวเองใช่ไหมครับ?  \n"
        "ที่นี่เรามีครบ — ไม่ว่าจะเป็น 🏋️‍♂️ แผ่นรองพื้น EVA, ยางยืดแรงต้าน, บาร์ดึงข้อ หรืออุปกรณ์บอดี้เวทอื่น ๆ  \n\n"
        "🎯 จุดเด่นของเรา  \n"
        "• เลือกง่าย: ตอบคำถามแค่ 6 ข้อ  \n"
        "• ได้ของตรงใจ: แนะนำสินค้าที่เหมาะกับงบและเป้าหมาย  \n"
        "• ใช้งานได้จริง: เหมาะกับบ้าน, คอนโด และฟิตเนสทุกขนาด  \n\n"
        "พร้อมแล้วหรือยังครับ? 🚀  \n"
        "ตอบคำถามแรกได้เลย แล้วผมจะช่วยเลือกอุปกรณ์ที่ใช่สำหรับคุณ 💪  \n\n"
        f"{progress}\n{qtext}"
        )
        
        if qid in quick_map:
            quick_items = quick_map[qid] + extra_buttons_init
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=intro,
                    quick_reply=QuickReply(items=quick_items)
                )
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=intro)
            )
        return

    profile = user_profiles[user_id]

    # ---- check คำสั่งพิเศษ ----
    if message == "แก้คำตอบ":
        profile = user_profiles[user_id]
        if profile["current_q"] > 0:
            profile["current_q"] -= 1  # ย้อนกลับ 1 ข้อ
            qid = profile["questions"][profile["current_q"]]["id"]
            qtext = profile["questions"][profile["current_q"]]["text"]
            progress = get_progress_text(profile["current_q"]+1, len(profile["questions"]))

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"แก้คำตอบข้อนี้ได้เลยครับ\n{progress}\n{qtext}",
                    quick_reply=QuickReply(items=quick_map[qid] + extra_buttons)
                )
            )
        return

    elif message == "ข้าม":
        profile = user_profiles[user_id]
        profile["answers"][profile["questions"][profile["current_q"]]["id"]] = "ข้าม"
        profile["current_q"] += 1

        # ส่งคำถามถัดไป (เหมือน flow ปกติ)
        if profile["current_q"] < len(profile["questions"]):
            qid = profile["questions"][profile["current_q"]]["id"]
            qtext = profile["questions"][profile["current_q"]]["text"]
            progress = get_progress_text(profile["current_q"]+1, len(profile["questions"]))
            
            if qid in quick_map:
                quick_items = quick_map[qid] + extra_buttons
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=f"{progress}\n{qtext}",
                        quick_reply=QuickReply(items=quick_items)
                    )
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{progress}\n{qtext}")
                )
        else:
            profile["finished"] = True

    elif message == "สินค้าขายดี":
        best_sellers = search_products("ขายดี", top_k=5)
        send_product_carousel(event.reply_token, best_sellers)
        return

    # ---- เก็บคำตอบ ----
    if not profile["finished"]:
        qid = profile["questions"][profile["current_q"]]["id"]
        profile["answers"][qid] = message
        profile["current_q"] += 1

        if profile["current_q"] < len(profile["questions"]):
            qid = profile["questions"][profile["current_q"]]["id"]
            qtext = profile["questions"][profile["current_q"]]["text"]
            progress = get_progress_text(profile["current_q"]+1, len(profile["questions"]))

            if qid in quick_map:
                quick_items = quick_map[qid] + extra_buttons
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=f"{progress}\n{qtext}",
                        quick_reply=QuickReply(items=quick_items)
                    )
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{progress}\n{qtext}")
                )

        else:
            profile["finished"] = True

    # ---- เมื่อครบ 6 ข้อ → สร้าง query text ----
    query_text = " ".join(profile["answers"].values())
    results = search_products(query_text, top_k=5)

    if not results:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ไม่พบสินค้าที่ตรงเงื่อนไขครับ 😥"))
        return

    # ---- สร้าง carousel แสดงสินค้า ----
    columns = []
    for r in results:
        col = CarouselColumn(
            title=r["name"][:40],
            text=f"ราคา: {r['price']}" if r.get("price") else "N/A",
            thumbnail_image_url=r.get("image_url"),
            actions=[URITemplateAction(label="ดูรายละเอียด", uri=r["url"])]
        )
        columns.append(col)

    carousel = TemplateSendMessage(
        alt_text="สินค้าแนะนำ",
        template=CarouselTemplate(columns=columns)
    )
    line_bot_api.reply_message(event.reply_token, carousel)

if __name__ == "__main__":
    app.run(port=5000)

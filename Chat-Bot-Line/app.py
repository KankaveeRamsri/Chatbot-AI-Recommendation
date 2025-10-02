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
from linebot.models import QuickReply, QuickReplyButton, MessageAction,TemplateSendMessage, CarouselTemplate, CarouselColumn, URITemplateAction, TextSendMessage, PostbackAction, PostbackEvent
from datetime import datetime

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
    {"id": "frequency", "text": "คุณออกกำลังกายบ่อยแค่ไหน? (1-2 ครั้ง/สัปดาห์, 3-5 ครั้ง, ทุกวัน)"},
    {"id": "safety", "text": "คุณกังวลเรื่องความปลอดภัยแบบไหน? (กันลื่น, กันกระแทก, ไม่สำคัญ)"},
    {"id": "brand", "text": "คุณสนใจแบรนด์เฉพาะหรือไม่? (Homefitt, Fittools, ไม่สำคัญ)"}
]

question_variants = {
    "budget": [
        "คุณมีงบประมาณเท่าไหร่? (เช่น ไม่เกิน 500 / 500-1000 / 1000+)",
        "โดยประมาณแล้ว คุณอยากใช้เงินเท่าไหร่ครับ?",
        "งบที่คุณตั้งไว้สำหรับอุปกรณ์นี้อยู่ที่ช่วงไหน?",
        "คุณคิดไว้ว่าจะลงทุนกับอุปกรณ์นี้เท่าไหร่ดี?"
    ],
    "place": [
        "คุณอยากใช้สินค้านี้ที่ไหน? (บ้าน, ฟิตเนส, สนามกีฬา)",
        "ปกติแล้วคุณจะใช้งานอุปกรณ์นี้ที่สถานที่ไหนครับ?",
        "คุณวางแผนจะนำอุปกรณ์นี้ไปใช้ที่ไหนเป็นหลัก?",
        "อุปกรณ์นี้จะถูกใช้งานในที่ใดครับ? (บ้าน, ฟิตเนส, สนามกีฬา)"
    ],
    "size": [
        "คุณอยากได้สินค้าขนาดเท่าไหร่? (เล็ก, กลาง, ใหญ่)",
        "คุณต้องการอุปกรณ์ขนาดเล็ก กลาง หรือใหญ่ครับ?",
        "ขนาดของอุปกรณ์ที่คุณสนใจควรเป็นแบบไหน?",
        "คุณคิดว่าขนาดใดเหมาะกับคุณที่สุด? (เล็ก/กลาง/ใหญ่)"
    ],
    "feature": [
        "คุณต้องการคุณสมบัติเด่นแบบไหน? (ลดแรงกระแทก, ทำความสะอาดง่าย, ทนความร้อน)",
        "อุปกรณ์นี้ควรมีคุณสมบัติพิเศษแบบใดที่คุณให้ความสำคัญ?",
        "คุณอยากให้อุปกรณ์มีจุดเด่นด้านใดครับ?",
        "ในบรรดาคุณสมบัติพิเศษ คุณให้ความสำคัญกับข้อไหน?"
    ],
    "material": [
        "คุณสนใจวัสดุอะไร? (EVA, ยาง, โฟม, ไม่ระบุ)",
        "วัสดุที่คุณอยากได้ควรเป็นแบบไหนครับ?",
        "คุณอยากให้ทำจาก EVA, ยาง, โฟม หรือไม่ระบุ?",
        "วัสดุของอุปกรณ์นี้มีผลต่อการตัดสินใจของคุณไหม?"
    ],
    "lifetime": [
        "คุณคาดหวังอายุการใช้งานกี่ปี? (1-2 ปี, 3-5 ปี, มากกว่า 5 ปี)",
        "คุณอยากให้อุปกรณ์นี้ใช้งานได้ประมาณกี่ปีครับ?",
        "อุปกรณ์นี้ควรใช้งานได้ในระยะเวลานานแค่ไหน?",
        "คุณคิดว่าอายุการใช้งานที่เหมาะสมควรอยู่ที่กี่ปี?"
    ],
    "color": [
        "คุณอยากเลือกสีไหม? (เทา, ดำ, ไม่สำคัญ)",
        "เรื่องสีของอุปกรณ์นี้สำคัญสำหรับคุณไหม?",
        "คุณมีสีที่ชอบหรืออยากเลือกไว้ล่วงหน้าหรือไม่?",
        "คุณอยากได้สีเทา ดำ หรือไม่ระบุ?"
    ],
    "value": [
        "คุณอยากได้แบบคุ้มค่าราคา หรือคุณภาพสูงสุด? (คุ้มค่า / คุณภาพสูงสุด)",
        "คุณให้ความสำคัญกับความคุ้มค่าหรือคุณภาพสูงกว่ากัน?",
        "สำหรับคุณแล้ว อะไรสำคัญกว่าระหว่างราคาและคุณภาพ?",
        "คุณอยากเน้นคุ้มค่าหรือเน้นคุณภาพสูงสุด?"
    ],
    "frequency": [
        "คุณออกกำลังกายบ่อยแค่ไหน? (1-2 ครั้ง/สัปดาห์, 3-5 ครั้ง, ทุกวัน)",
        "โดยทั่วไปคุณมักออกกำลังกายกี่ครั้งต่อสัปดาห์?",
        "คุณจัดตารางออกกำลังกายไว้บ่อยแค่ไหนครับ?",
        "คุณมักออกกำลังกายเป็นประจำทุกวัน หรือสัปดาห์ละกี่ครั้ง?"
    ],
    "safety": [
        "คุณกังวลเรื่องความปลอดภัยแบบไหน? (กันลื่น, กันกระแทก, ไม่สำคัญ)",
        "เรื่องความปลอดภัย คุณให้ความสำคัญด้านใดมากที่สุด?",
        "อุปกรณ์นี้ควรช่วยลดความเสี่ยงในเรื่องใด?",
        "คุณอยากให้เน้นป้องกันแบบไหนครับ? กันลื่น กันกระแทก หรือไม่ระบุ"
    ],
    "brand": [
        "คุณสนใจแบรนด์เฉพาะหรือไม่? (Homefitt, Fittools, ไม่สำคัญ)",
        "คุณอยากเลือกจากแบรนด์ไหนเป็นพิเศษหรือเปล่า?",
        "เรื่องแบรนด์มีผลต่อการเลือกของคุณไหม?",
        "คุณอยากได้ยี่ห้อเฉพาะ หรือไม่ซีเรียสเรื่องแบรนด์?"
    ]
}

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
            "frequency": [
                QuickReplyButton(action=MessageAction(label="1-2 ครั้ง/สัปดาห์", text="1-2 ครั้ง/สัปดาห์")),
                QuickReplyButton(action=MessageAction(label="3-5 ครั้ง/สัปดาห์", text="3-5 ครั้ง/สัปดาห์")),
                QuickReplyButton(action=MessageAction(label="ทุกวัน", text="ทุกวัน"))
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

# -------- Filter budget --------
def filter_products_by_budget(products, budget_answer):
    def parse_price(p):
        try:
            return int(p.get("price"))
        except (TypeError, ValueError):
            return None

    if "≤500" in budget_answer or "ไม่เกิน 500" in budget_answer:
        return [p for p in products if parse_price(p) is not None and parse_price(p) <= 500]
    elif "500-1000" in budget_answer:
        return [p for p in products if parse_price(p) is not None and 500 <= parse_price(p) <= 1000]
    elif "1000+" in budget_answer or "มากกว่า 1000" in budget_answer:
        return [p for p in products if parse_price(p) is not None and parse_price(p) >= 1000]
    return products

def clean_price(val):
    if not val:
        return None
    try:
        # เอาเฉพาะตัวเลขออกมา
        cleaned = "".join([c for c in str(val) if c.isdigit()])
        return int(cleaned) if cleaned else None
    except:
        return None

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
        products = []
        for record in result:
            data = record.data()

            # print("DEBUG PRICE:", data.get("price"))

            # clean price
            try:
                data["price"] = clean_price(data.get("price"))
            except:
                data["price"] = None
            products.append(data)
        return products


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
def build_product_carousel(products):
    if not products:
        return TextSendMessage(text="ไม่มีสินค้าตรงเงื่อนไขครับ")

    columns = []
    for p in products:
        col = CarouselColumn(
            title=(p.get("name") or "")[:40],
            text=f"ราคา: {p['price']:,} บาท" if p.get("price") else "ราคาไม่ระบุ",
            thumbnail_image_url=p.get("image_url"),
            actions=[
                PostbackAction(
                    label="ดูรายละเอียด",
                    data=f"view_product:{p.get('name','')}"
                )
            ]
        )
        columns.append(col)

    return TemplateSendMessage(
        alt_text="สินค้าแนะนำ",
        template=CarouselTemplate(columns=columns)
    )

# -------- สุ่มประโยค --------
def get_question_text(qid, default_text):
    if qid in question_variants:
        return random.choice(question_variants[qid])
    return default_text

def log_user_action(user_id, action, data=None):
    """
    บันทึกการกระทำของผู้ใช้ลง Neo4j
    :param user_id: ไอดีผู้ใช้ LINE
    :param action: ประเภท action เช่น 'answer', 'search', 'view_product', 'best_seller'
    :param data: ข้อมูลเพิ่มเติม (dict หรือ string)
    """
    timestamp = datetime.now().isoformat()

    with driver.session() as session:
        query = """
        MERGE (u:User {id: $user_id})
        CREATE (l:Log {
            action: $action,
            data: $data,
            timestamp: $timestamp
        })
        MERGE (u)-[:HAS_LOG]->(l)
        """
        session.run(query, user_id=user_id, action=action, data=str(data), timestamp=timestamp)

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data or ""

    if data.startswith("view_product:"):
        product_name = data[len("view_product:"):]  # สิ่งที่เราส่งมา
        # หา product จาก list ที่มีอยู่ (หรือจะไป query Neo4j ก็ได้)
        product = next((p for p in products if (p.get("name") == product_name)), None)

        # log ก่อน
        log_user_action(user_id, "view_product", {
            "product_name": product_name,
            "url": (product.get("url") if product else None)
        })

        # ตอบกลับพร้อมลิงก์ถ้ามี
        if product and product.get("url"):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"คุณเลือกดูสินค้า: {product_name}\n👉 {product['url']}")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"คุณเลือกดูสินค้า: {product_name}\nขออภัย ไม่พบลิงก์สินค้า")
            )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    message = event.message.text.strip()

    # ---- init session ----
    if user_id not in user_profiles:
        # fix ให้ budget อยู่เสมอ
        must_have = next(q for q in all_questions if q["id"] == "budget")
        other_qs = [q for q in all_questions if q["id"] != "budget"]

        # เลือกสุ่มเพิ่มจากข้ออื่น ๆ
        selected = [must_have] + random.sample(other_qs, 6)

        user_profiles[user_id] = {
            "questions": selected,
            "answers": {},
            "current_q": 0,
            "finished": False
        }

        qid = selected[0]["id"]
        qtext = get_question_text(qid, selected[0]["text"])
        progress = get_progress_text(1, len(selected))

        intro = (
        "สวัสดีครับ 🙌  \n"
        "ยินดีต้อนรับสู่ FitBot 🤖 ผู้ช่วยเลือกอุปกรณ์บอดี้เวทสำหรับคุณ  \n\n"
        "คุณอยากเริ่มออกกำลังกาย แต่ไม่แน่ใจว่าอุปกรณ์แบบไหนเหมาะกับตัวเองใช่ไหมครับ?  \n"
        "ที่นี่เรามีครบ — ไม่ว่าจะเป็น 🏋️‍♂️ แผ่นรองพื้น EVA, ยางยืดแรงต้าน, บาร์ดึงข้อ หรืออุปกรณ์บอดี้เวทอื่น ๆ  \n\n"
        "🎯 จุดเด่นของเรา  \n"
        "• เลือกง่าย: ตอบคำถามแค่ 7 ข้อ  \n"
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
        answered_qs = profile["answers"].keys()

        quick_items = []
        for idx, q in enumerate(profile["questions"], start=1):
            if q["id"] in answered_qs:
                quick_items.append(
                    QuickReplyButton(action=MessageAction(label=f"ข้อ {idx}", text=f"แก้:{q['id']}"))
                )

        # บันทึกตำแหน่งปัจจุบันเอาไว้ก่อน
        profile["resume_q"] = profile["current_q"]

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="คุณอยากแก้คำตอบข้อไหนครับ? 🔄",
                quick_reply=QuickReply(items=quick_items)
            )
        )
        return

    # กรณีเลือกแก้ข้อที่ระบุ
    elif message.startswith("แก้:"):
        profile = user_profiles[user_id]
        qid = message.replace("แก้:", "")
        
        # ตั้ง current_q ชั่วคราวเป็นข้อที่เลือกมาแก้
        for idx, q in enumerate(profile["questions"]):
            if q["id"] == qid:
                profile["current_q"] = idx
                break

        qtext = get_question_text(qid, [q for q in all_questions if q["id"] == qid][0]["text"])
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
            qtext = get_question_text(qid, profile["questions"][profile["current_q"]]["text"])
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
                return
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{progress}\n{qtext}")
                )
        else:
            profile["finished"] = True

    elif message == "สินค้าขายดี":
        best_sellers = search_products("ขายดี", top_k=5)
        log_user_action(user_id, "best_seller", {"results": [p["name"] for p in best_sellers]})

        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="นี่คือสินค้าขายดี 👇"),
                build_product_carousel(best_sellers),
                TextSendMessage(
                    text="อยากเริ่มต้นใหม่อีกรอบไหมครับ? ✨ พิมพ์ 'เริ่มใหม่' แล้วไปกันต่อเลย!",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="🔄 เริ่มใหม่", text="เริ่มใหม่"))
                    ])
                )
            ]
        )
        return

    elif message == "เริ่มใหม่":
        # reset session
        if user_id in user_profiles:
            del user_profiles[user_id]

        # สร้าง session ใหม่
        must_have = next(q for q in all_questions if q["id"] == "budget")
        other_qs = [q for q in all_questions if q["id"] != "budget"]
        selected = [must_have] + random.sample(other_qs, 6)

        user_profiles[user_id] = {
            "questions": selected,
            "answers": {},
            "current_q": 0,
            "finished": False
        }

        qid = selected[0]["id"]
        qtext = get_question_text(qid, selected[0]["text"])
        progress = get_progress_text(1, len(selected))

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"🎉 เริ่มใหม่กันเลย!\n{progress}\n{qtext}",
                quick_reply=QuickReply(items=quick_map[qid] + extra_buttons_init)
            )
        )
        return

    # ---- เก็บคำตอบ ----
    if not profile["finished"]:
        qid = profile["questions"][profile["current_q"]]["id"]

        # --- ตรวจว่าคำตอบ valid ไหม ---
        valid_answers = [btn.action.text for btn in quick_map.get(qid, [])]
        special_cmds = ["แก้คำตอบ", "ข้าม", "สินค้าขายดี", "เริ่มใหม่"]

        if message not in valid_answers and message not in special_cmds:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"⛔ คำตอบไม่ถูกต้องครับ กรุณาเลือกจากตัวเลือกด้านล่าง\n{get_progress_text(profile['current_q']+1, len(profile['questions']))}\n{get_question_text(qid, [q for q in all_questions if q['id']==qid][0]['text'])}",
                    quick_reply=QuickReply(items=quick_map.get(qid, []) + extra_buttons)
                )
            )
            return

        profile["answers"][qid] = message
        log_user_action(user_id, "answer", {"question_id": qid, "answer": message})

        # ถ้าเป็นการแก้ไข → กลับไป resume_q
        if "resume_q" in profile:
            profile["current_q"] = profile["resume_q"]
            del profile["resume_q"]
        else:
            profile["current_q"] += 1

        if profile["current_q"] < len(profile["questions"]):
            qid = profile["questions"][profile["current_q"]]["id"]
            qtext = get_question_text(qid, profile["questions"][profile["current_q"]]["text"])
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
                return
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{progress}\n{qtext}")
                )

        else:
            profile["finished"] = True

    # ---- เมื่อครบ 7 ข้อ → สร้าง query text ----
    query_text = " ".join(profile["answers"].values())

    # --- filter ก่อนด้วย budget ---
    budget_answer = profile["answers"].get("budget", "")
    filtered_products = filter_products_by_budget(products, budget_answer)

    fallback = False
    if not filtered_products:
        filtered_products = products
        fallback = True

    # --- semantic search บน subset ---
    texts = [f"{p['name']} {p['description']} {p['price']}" for p in filtered_products]
    embeds = model.encode(texts, normalize_embeddings=True)
    sub_index = faiss.IndexFlatIP(embeds.shape[1])
    sub_index.add(embeds)

    query_vec = model.encode([query_text], normalize_embeddings=True)
    distances, indices = sub_index.search(query_vec, min(5, len(filtered_products)))
    results = [filtered_products[i] for i in indices[0]]
    
    log_user_action(user_id, "search", {"query": query_text, "results": [p["name"] for p in results]})
    
    # ---- เตรียมสรุปคำตอบ ----
    summary_lines = ["สรุปคำตอบของคุณนะครับ 👇"]
    for idx, q in enumerate(profile["questions"], start=1):
        qid = q["id"]
        ans = profile["answers"].get(qid, "ไม่ระบุ")
        summary_lines.append(f"- ข้อ {idx}: {ans}")

    summary_text = "\n".join(summary_lines)

    # ---- สร้าง messages แล้ว reply "ครั้งเดียว" ----
    if not results:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=summary_text), TextSendMessage(text="ไม่พบสินค้าที่ตรงเงื่อนไขครับ 😥"))
        return

    carousel_msg = build_product_carousel(results)

    if fallback:
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=summary_text),
            TextSendMessage(text="ไม่พบสินค้าที่ตรงงบเป๊ะ ๆ ครับ 😅 แต่ผมแนะนำที่ใกล้เคียงให้แทน 👇"),
            carousel_msg
        ])
        return
    else:
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=summary_text),
            TextSendMessage(text="นี่คือสินค้าที่เหมาะกับคุณ 👇"),
            carousel_msg,
            TextSendMessage(
                text="อยากเริ่มต้นใหม่อีกรอบไหมครับ? ✨ พิมพ์ 'เริ่มใหม่' แล้วไปกันต่อเลย!",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="🔄 เริ่มใหม่", text="เริ่มใหม่"))
                ])
            )
        ])
        return

if __name__ == "__main__":
    app.run(port=5000)

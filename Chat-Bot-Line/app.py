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
    {"id": "value", "text": "คุณอยากได้แบบคุ้มค่าราคา หรือคุณภาพสูงสุด? (คุ้มค่า / คุณภาพสูงสุด)"}
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
            ]
        }

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    message = event.message.text.strip()

    # ---- init session ----
    if user_id not in user_profiles:
        selected = random.sample(all_questions, 6)
        user_profiles[user_id] = {
            "questions": selected,
            "answers": {},
            "current_q": 0,
            "finished": False
        }

        qid = selected[0]["id"]
        qtext = selected[0]["text"]

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
        f"{qtext}"
        )
        
        if qid in quick_map:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=intro,
                    quick_reply=QuickReply(items=quick_map[qid])
                )
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=intro)
            )
        return

    profile = user_profiles[user_id]

    # ---- เก็บคำตอบ ----
    if not profile["finished"]:
        qid = profile["questions"][profile["current_q"]]["id"]
        profile["answers"][qid] = message
        profile["current_q"] += 1

        if profile["current_q"] < len(profile["questions"]):
            qid = profile["questions"][profile["current_q"]]["id"]
            qtext = profile["questions"][profile["current_q"]]["text"]

            if qid in quick_map:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text=qtext,
                        quick_reply=QuickReply(items=quick_map[qid])
                    )
                )
            else:
                # ถ้าไม่มี quick reply ให้ส่งเป็น text ธรรมดา
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=qtext))
            return

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
            text=r["price"] or "N/A",
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

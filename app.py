import json
import os
import urllib.parse
import urllib.request

from flask import Flask, abort, jsonify, request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
API = f"https://api.telegram.org/bot{TOKEN}/"

app = Flask(__name__)

MENU = {
    "keyboard": [
        [{"text": "📚 သင်တန်းအမျိုးအစား"}, {"text": "💰 Package & Fees"}],
        [{"text": "🌙 Zoom ညတန်း"}, {"text": "🏫 အပြင်တန်း"}],
        [{"text": "📝 အပ်နှံရန်"}, {"text": "🎯 Exam Support"}],
        [{"text": "📍 ကျောင်းလိပ်စာ"}, {"text": "☎️ ဆက်သွယ်ရန်"}],
    ],
    "resize_keyboard": True,
}

ANSWERS = {
    "courses": (
        "📚 MEPT သင်တန်းအမျိုးအစား ၂ မျိုးရှိပါတယ်။\n\n"
        "1️⃣ Online Zoom Live Class — ညဘက် အိမ်ကနေတက်နိုင်ပါတယ်။\n"
        "2️⃣ In-person Class — လှိုင်မြို့နယ်ရှိ သင်တန်းကျောင်းမှာ တက်ရောက်ရပါတယ်။\n\n"
        "သင်တန်းအားလုံးက ၁ လပြတ်၊ တစ်ပတ် ၄ ရက်ဖြစ်ပြီး Speaking, Reading, "
        "Writing, Listening 4 Skills ကို စနစ်တကျ လေ့ကျင့်ပေးပါတယ်။"
    ),
    "fees": (
        "💰 Package ၂ မျိုးရှိပါတယ်။\n\n"
        "🔹 Standard — ၂၅၀,၀၀၀ ကျပ်\n"
        "🔸 Premium — ၃၅၀,၀၀၀ ကျပ် ⭐ Recommended\n\n"
        "Premium မှာ Zoom/Home-study support နဲ့ Premium Seaman Service website "
        "ပေါ်က Lessons, Exercises, Courses များပါဝင်ပါတယ်။\n\n"
        "သင်တန်းကြေးက ၁ လစာဖြစ်ပြီး Exam Fee က သီးခြား one-time charge ဖြစ်ပါတယ်။"
    ),
    "zoom": (
        "🌙 Online Zoom Live Class\n\n"
        "• အလုပ်မပျက်ဘဲ ညဘက် အိမ်ကနေတက်နိုင်ပါတယ်။\n"
        "• သင်တန်းကာလ — ၁ လပြတ်\n"
        "• တစ်ပတ် — ၄ ရက်\n"
        "• တစ်ရက် — ၂ နာရီ Zoom Live Class\n"
        "• တက်ရောက်ရမယ့်ရက်များကို အတန်းစတင်ချိန်မှာ ညှိနှိုင်းပေးပါတယ်။\n\n"
        "Standard — ၂၅၀,၀၀၀ ကျပ်\nPremium — ၃၅၀,၀၀၀ ကျပ်"
    ),
    "inperson": (
        "🏫 In-person Class\n\n"
        "• လှိုင်မြို့နယ်ရှိ သင်တန်းကျောင်းမှာ စနစ်တကျ သင်ကြားပါတယ်။\n"
        "• သင်တန်းကာလ — ၁ လပြတ်\n• တစ်ပတ် — ၄ ရက်\n\n"
        "Standard — ၂၅၀,၀၀၀ ကျပ်\nPremium — ၃၅၀,၀၀၀ ကျပ် ⭐\n"
        "Premium မှာ အပြင်တန်း + ညဘက် Zoom/Home-study support ပါဝင်တဲ့ "
        "Hybrid System ဖြစ်ပါတယ်။"
    ),
    "premium": (
        "⭐ Premium Package — ၃၅၀,၀၀၀ ကျပ်\n\n"
        "• ၁ လစာ Home-study lessons\n"
        "• Speaking, Reading, Writing, Listening 4 Skills practice\n"
        "• Premium Seaman Service website မှ Lessons, Exercises, Courses\n"
        "• အချိန်မရွေး စာပြန်နွေးနိုင်ခြင်း\n"
        "• In-person Premium အတွက် အပြင်တန်း + Zoom Hybrid Support\n"
        "• Form submission, Exam Center support နဲ့ အခမဲ့ ၂ ရက် Revision Class"
    ),
    "standard": (
        "🔹 Standard Package — ၂၅၀,၀၀၀ ကျပ်\n\n"
        "Online Standard မှာ တစ်ပတ် ၄ ရက်၊ တစ်ရက် ၂ နာရီ Zoom Live Class "
        "တက်ရောက်နိုင်ပါတယ်။ In-person Standard မှာ ကျောင်း၌ စနစ်တကျ "
        "သင်ကြားပေးပါတယ်။\n\n"
        "Form submission, Exam Center support နဲ့ အခမဲ့ ၂ ရက် Revision Class ပါဝင်ပါတယ်။"
    ),
    "exam": (
        "🎯 Standard နဲ့ Premium နှစ်မျိုးလုံးမှာ Exam Support ပါဝင်ပါတယ်။\n\n"
        "✅ ရုံးအဖွဲ့က Form တင်ခြင်းကို အစအဆုံး ကူညီပေးပါတယ်။\n"
        "✅ Exam Center နဲ့ ချိတ်ဆက်ဆောင်ရွက်ပေးပါတယ်။\n"
        "✅ Exam ရက်နီးလာရင် ၂ ရက် Revision Class အခမဲ့တက်နိုင်ပါတယ်။\n"
        "✅ Mock Tests နဲ့ 4 Skills လေ့ကျင့်မှုများ ပါဝင်ပါတယ်။"
    ),
    "register": (
        "📝 အပ်နှံရန်လိုအပ်ချက်\n\n"
        "• စရံငွေ — ၅၀,၀၀၀ ကျပ်\n"
        "• မိမိနာမည်\n• ဖုန်းနံပါတ်\n• ရွေးချယ်လိုသော Class/Package\n\n"
        "နေရာအကန့်အသတ်ရှိလို့ စရံငွေကြိုတင်ပေးသွင်းသူများကို ဦးစားပေးပါတယ်။ "
        "ငွေလွှဲရန် account information ကို MEPT staff ဆီ တိုက်ရိုက်မေးမြန်းပါ။"
    ),
    "address": (
        "📍 MEPT သင်တန်းကျောင်းလိပ်စာ\n\n"
        "အိမ်နံပါတ် (၆၀)၊ မာလာမြိုင် (၈) လမ်း၊ အရှေ့ဗဟိုလမ်းအနီး၊ "
        "လှိုင်မြို့နယ်၊ ရန်ကုန်မြို့။"
    ),
    "contact": (
        "☎️ MEPT team ကို ဆက်သွယ်ရန်\n\n"
        "မိမိနာမည်၊ ဖုန်းနံပါတ်၊ တက်လိုသော Class/Package နဲ့ မေးခွန်းကို "
        "Message တစ်စောင်တည်းမှာ ပို့ပေးပါ။ Staff က ပြန်လည်ဆက်သွယ်ပေးပါမယ်။"
    ),
}


def telegram(method, payload=None):
    data = urllib.parse.urlencode(payload or {}).encode()
    with urllib.request.urlopen(API + method, data=data, timeout=15) as response:
        return json.load(response)


def send(chat_id, text):
    telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": json.dumps(MENU),
        },
    )


def answer(text):
    q = text.strip().lower()
    if q.startswith(("/start", "/help")):
        return "မင်္ဂလာပါ 👋\nWelcome to MEPT Student Support.\n\nအောက်က Menu မှ ရွေးချယ်ပါ။"
    if "premium" in q:
        return ANSWERS["premium"]
    if "standard" in q:
        return ANSWERS["standard"]
    if any(x in q for x in ("fee", "price", "package", "ကြေး")):
        return ANSWERS["fees"]
    if any(x in q for x in ("zoom", "ညတန်း", "online")):
        return ANSWERS["zoom"]
    if any(x in q for x in ("အပြင်တန်း", "in-person", "inperson")):
        return ANSWERS["inperson"]
    if any(x in q for x in ("register", "အပ်နှံ", "စာရင်း", "စရံ")):
        return ANSWERS["register"]
    if any(x in q for x in ("address", "လိပ်စာ", "location")):
        return ANSWERS["address"]
    if any(x in q for x in ("exam", "စာမေးပွဲ", "revision", "form")):
        return ANSWERS["exam"]
    if any(x in q for x in ("contact", "phone", "ဆက်သွယ်")):
        return ANSWERS["contact"]
    if any(x in q for x in ("course", "class", "သင်တန်း")):
        return ANSWERS["courses"]
    return (
        "မေးခွန်းကို လက်ခံရရှိပါတယ်။ MEPT team က ပြန်လည်ကူညီပေးပါမယ်။\n\n"
        "For a faster answer, choose one of the menu buttons below."
    )


@app.get("/")
def health():
    return jsonify(status="ok", service="MEPT Student Support Bot")


@app.post("/telegram/<secret>")
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    update = request.get_json(silent=True) or {}
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")
    if chat_id is not None and text:
        send(chat_id, answer(text))
    return jsonify(ok=True)


import base64
import json
import os
import secrets
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, Response, abort, jsonify, redirect, render_template_string, request, url_for


TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/tmp/mept-leads.db")
API = f"https://api.telegram.org/bot{TOKEN}/"
K_PAY_NUMBER = "09886295282"
K_PAY_NAME = "Myat Phone Kyaw"

app = Flask(__name__)

HOME_MENU = {
    "keyboard": [
        [{"text": "🏫 In-person Class"}, {"text": "🌙 Online Class"}],
        [{"text": "❓ FAQs"}, {"text": "📍 လိပ်စာ / ဆက်သွယ်ရန်"}],
    ],
    "resize_keyboard": True,
}

INPERSON_MENU = {
    "keyboard": [
        [{"text": "🏫 In-person Standard"}, {"text": "⭐ In-person Premium"}],
        [{"text": "⬅️ Main Menu"}],
    ],
    "resize_keyboard": True,
}

ONLINE_MENU = {
    "keyboard": [
        [{"text": "🌙 Online Standard"}, {"text": "💎 Online Premium"}],
        [{"text": "⬅️ Main Menu"}],
    ],
    "resize_keyboard": True,
}

FAQ_MENU = {
    "keyboard": [
        [{"text": "🕐 အတန်းချိန်"}, {"text": "🎯 Exam Support"}],
        [{"text": "💳 Payment ဘယ်လိုလုပ်မလဲ"}, {"text": "⬅️ Main Menu"}],
    ],
    "resize_keyboard": True,
}

PAYMENT_MENU = {
    "keyboard": [
        [{"text": "📱 ဖုန်းနံပါတ်ပို့မယ်", "request_contact": True}],
        [{"text": "⬅️ Main Menu"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}

PACKAGE_DETAILS = {
    "inperson-standard": {
        "label": "In-person Standard",
        "class_type": "In-person",
        "package": "Standard",
        "fee": 220000,
        "details": (
            "🏫 In-person Standard — ၂၂၀,၀၀၀ ကျပ်\n\n"
            "• ကျောင်းတွင် ဆရာ/ဆရာမများနှင့် တိုက်ရိုက်တက်ရောက်ရမည့်အတန်း\n"
            "• တစ်ပတ် ၄ ရက်\n"
            "• ချပေးထားသောရက်များထဲမှ အဆင်ပြေသည့်ရက်ကို ရွေးနိုင်ပါတယ်\n"
            "• Exam Form နှင့် Exam Center support ပါဝင်ပါတယ်"
        ),
    },
    "inperson-premium": {
        "label": "In-person Premium",
        "class_type": "In-person",
        "package": "Premium",
        "fee": 290000,
        "details": (
            "⭐ In-person Premium — ၂၉၀,၀၀၀ ကျပ်\n\n"
            "• In-person Standard အားလုံးပါဝင်ပါတယ်\n"
            "• ၁ လစာ Home Study Lessons\n"
            "• Speaking, Reading, Writing, Listening 4 Skills practice\n"
            "• Online learning support နှင့် interactive exercises\n"
            "• Exam Form နှင့် Exam Center support ပါဝင်ပါတယ်"
        ),
    },
    "online-standard": {
        "label": "Online Standard",
        "class_type": "Online",
        "package": "Standard",
        "fee": 220000,
        "details": (
            "🌙 Online Standard — ၂၂၀,၀၀၀ ကျပ်\n\n"
            "• Zoom Live Class\n"
            "• တစ်ပတ် ၄ ရက်\n"
            "• ည ၈:၀၀–၉:၃၀ သို့မဟုတ် ည ၉:၃၀–၁၁:၀၀\n"
            "• အဆင်ပြေသည့်အချိန်ကို ရွေးနိုင်ပါတယ်\n"
            "• Exam Form နှင့် Exam Center support ပါဝင်ပါတယ်"
        ),
    },
    "online-premium": {
        "label": "Online Premium",
        "class_type": "Online",
        "package": "Premium",
        "fee": 290000,
        "details": (
            "💎 Online Premium — ၂၉၀,၀၀၀ ကျပ်\n\n"
            "• Zoom Live Class — တစ်ပတ် ၄ ရက်\n"
            "• ည ၈:၀၀–၉:၃၀ သို့မဟုတ် ည ၉:၃၀–၁၁:၀၀\n"
            "• ၁ လစာ Home Study Lessons\n"
            "• Premium Seaman Service Website access\n"
            "• 4 Skills interactive exercises & courses\n"
            "• Exam Form နှင့် Exam Center support ပါဝင်ပါတယ်"
        ),
    },
}


def db():
    parent = os.path.dirname(DATABASE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                chat_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                full_name TEXT,
                phone TEXT,
                class_type TEXT,
                package TEXT,
                fee INTEGER,
                status TEXT NOT NULL DEFAULT 'New',
                payment_file_id TEXT,
                payment_submitted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def telegram(method, payload=None):
    data = urllib.parse.urlencode(payload or {}).encode()
    with urllib.request.urlopen(API + method, data=data, timeout=20) as response:
        return json.load(response)


def send(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    telegram("sendMessage", payload)


def upsert_identity(message):
    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    full_name = " ".join(
        part for part in (sender.get("first_name"), sender.get("last_name")) if part
    )
    stamp = now()
    with db() as connection:
        connection.execute(
            """
            INSERT INTO leads
                (chat_id, telegram_username, full_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'New', ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                telegram_username=excluded.telegram_username,
                full_name=CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE leads.full_name END,
                updated_at=excluded.updated_at
            """,
            (chat_id, sender.get("username"), full_name, stamp, stamp),
        )
    return chat_id


def select_package(chat_id, key):
    item = PACKAGE_DETAILS[key]
    with db() as connection:
        connection.execute(
            """
            UPDATE leads SET class_type=?, package=?, fee=?, status='Interested',
                payment_file_id=NULL, payment_submitted_at=NULL, updated_at=?
            WHERE chat_id=?
            """,
            (item["class_type"], item["package"], item["fee"], now(), chat_id),
        )
    send(
        chat_id,
        item["details"]
        + "\n\nအပ်နှံလိုပါက အောက်က 💳 Payment လုပ်မယ် ကိုနှိပ်ပါ။",
        {
            "keyboard": [
                [{"text": "💳 Payment လုပ်မယ်"}, {"text": "❓ FAQs"}],
                [{"text": "⬅️ Main Menu"}],
            ],
            "resize_keyboard": True,
        },
    )


def payment_instructions(chat_id):
    with db() as connection:
        lead = connection.execute(
            "SELECT class_type, package, fee FROM leads WHERE chat_id=?", (chat_id,)
        ).fetchone()
        if not lead or not lead["package"]:
            send(chat_id, "Payment မလုပ်ခင် Class နှင့် Package ကိုအရင်ရွေးပါ။", HOME_MENU)
            return
        connection.execute(
            "UPDATE leads SET status='Payment Started', updated_at=? WHERE chat_id=?",
            (now(), chat_id),
        )
    send(
        chat_id,
        (
            f"💳 KPay ဖြင့် ငွေပေးချေရန်\n\n"
            f"ဖုန်းနံပါတ် — {K_PAY_NUMBER}\n"
            f"အမည် — {K_PAY_NAME}\n"
            f"ကျသင့်ငွေ — {lead['fee']:,} ကျပ်\n\n"
            "1️⃣ အောက်က ဖုန်းနံပါတ်ပို့မယ် ကိုနှိပ်ပါ\n"
            "2️⃣ KPay ငွေလွှဲပြီး Payment Screenshot ကို ဒီ chat ထဲ Photo အဖြစ်တင်ပါ\n\n"
            "Screenshot ရလာတာနဲ့ MEPT staff ကစစ်ပြီး အတည်ပြုပေးပါမယ်။"
        ),
        PAYMENT_MENU,
    )


def handle_contact(chat_id, contact):
    phone = contact.get("phone_number", "").strip()
    if not phone:
        return
    with db() as connection:
        connection.execute(
            "UPDATE leads SET phone=?, updated_at=? WHERE chat_id=?",
            (phone, now(), chat_id),
        )
    send(
        chat_id,
        "ဖုန်းနံပါတ် လက်ခံရရှိပါတယ် ✅\nအခု KPay Payment Screenshot ကို Photo အဖြစ်တင်ပေးပါ။",
        PAYMENT_MENU,
    )


def handle_photo(chat_id, photos):
    if not photos:
        return
    file_id = photos[-1].get("file_id")
    if not file_id:
        return
    stamp = now()
    with db() as connection:
        lead = connection.execute(
            "SELECT package FROM leads WHERE chat_id=?", (chat_id,)
        ).fetchone()
        if not lead or not lead["package"]:
            send(chat_id, "Screenshot မတင်ခင် Class နှင့် Package ကိုအရင်ရွေးပါ။", HOME_MENU)
            return
        connection.execute(
            """
            UPDATE leads SET payment_file_id=?, payment_submitted_at=?,
                status='Payment Review', updated_at=? WHERE chat_id=?
            """,
            (file_id, stamp, stamp, chat_id),
        )
    send(
        chat_id,
        (
            "Payment Screenshot လက်ခံရရှိပါတယ် ✅\n\n"
            "MEPT staff ကငွေလွှဲကိုစစ်ပြီး အတည်ပြုပေးပါမယ်။ "
            "ဖုန်းနံပါတ်မပို့ရသေးပါက အောက်က button ကိုနှိပ်ပေးပါ။"
        ),
        PAYMENT_MENU,
    )


def handle_text(chat_id, text):
    q = text.strip().lower()
    if q.startswith(("/start", "/help")) or "main menu" in q:
        send(
            chat_id,
            "မင်္ဂလာပါ 👋\nMEPT Student Support မှကြိုဆိုပါတယ်။\n\nတက်လိုသည့် Class Type ကိုရွေးပါ။",
            HOME_MENU,
        )
    elif "in-person standard" in q:
        select_package(chat_id, "inperson-standard")
    elif "in-person premium" in q:
        select_package(chat_id, "inperson-premium")
    elif "online standard" in q:
        select_package(chat_id, "online-standard")
    elif "online premium" in q:
        select_package(chat_id, "online-premium")
    elif "in-person" in q or "inperson" in q or "အပြင်တန်း" in q:
        send(
            chat_id,
            (
                "🏫 In-person Class\n\n"
                "တက်ရမည့်နေ့စပြီး ချပေးထားသောရက်များထဲမှ "
                "မိမိအဆင်ပြေသည့်ရက်ကို ရွေးနိုင်ပါတယ်။\n\nPackage ကိုရွေးပါ။"
            ),
            INPERSON_MENU,
        )
    elif "online class" in q or "zoom" in q or "ညတန်း" in q:
        send(
            chat_id,
            (
                "🌙 Online Zoom Live Class\n\n"
                "• ည ၈:၀၀–၉:၃၀\n"
                "• ည ၉:၃၀–၁၁:၀၀\n"
                "• တစ်ပတ် ၄ ရက်\n\n"
                "အဆင်ပြေသည့်အချိန်နှင့် Package ကိုရွေးနိုင်ပါတယ်။"
            ),
            ONLINE_MENU,
        )
    elif "payment" in q or "ငွေ" in q or "kpay" in q:
        payment_instructions(chat_id)
    elif "အတန်းချိန်" in q or "schedule" in q or "အချိန်" in q:
        send(
            chat_id,
            (
                "🕐 အတန်းချိန်\n\n"
                "🏫 In-person — ချပေးထားသောရက်များထဲမှ အဆင်ပြေသည့်ရက်ရွေးနိုင်ပါတယ်။\n\n"
                "🌙 Online — ည ၈:၀၀–၉:၃၀ သို့မဟုတ် ည ၉:၃၀–၁၁:၀၀၊ တစ်ပတ် ၄ ရက်။"
            ),
            FAQ_MENU,
        )
    elif "exam" in q or "စာမေးပွဲ" in q:
        send(
            chat_id,
            (
                "🎯 Standard နှင့် Premium နှစ်မျိုးလုံးမှာ Exam Form submission၊ "
                "Exam Center support နှင့် Revision support ပါဝင်ပါတယ်။"
            ),
            FAQ_MENU,
        )
    elif "faq" in q or "မေး" in q:
        send(chat_id, "သိလိုသည့်အကြောင်းအရာကို ရွေးပါ။", FAQ_MENU)
    elif "လိပ်စာ" in q or "ဆက်သွယ်" in q or "address" in q:
        send(
            chat_id,
            (
                "📍 အိမ်နံပါတ် (၆၀)၊ မာလာမြိုင် (၈) လမ်း၊ "
                "အရှေ့ဗဟိုလမ်းအနီး၊ လှိုင်မြို့နယ်၊ ရန်ကုန်မြို့။"
            ),
            HOME_MENU,
        )
    else:
        send(chat_id, "အောက်က Menu မှ သင်တန်းအမျိုးအစားကိုရွေးပါ။", HOME_MENU)


def require_dashboard_auth(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        valid = (
            bool(DASHBOARD_PASSWORD)
            and auth
            and auth.username == "mept"
            and secrets.compare_digest(auth.password, DASHBOARD_PASSWORD)
        )
        if not valid:
            return Response(
                "Login required",
                401,
                {"WWW-Authenticate": 'Basic realm="MEPT Lead Dashboard"'},
            )
        return function(*args, **kwargs)

    return wrapped


DASHBOARD_HTML = """
<!doctype html>
<html lang="my">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MEPT Lead Dashboard</title>
  <style>
    :root{--navy:#102d4e;--blue:#1677ff;--green:#0b9b6f;--amber:#e89a16;--red:#d14343;--bg:#f4f7fb;--card:#fff;--text:#162033;--muted:#687386}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,"Noto Sans Myanmar",sans-serif}
    header{background:var(--navy);color:white;padding:24px clamp(20px,5vw,64px)}header h1{margin:0;font-size:25px}header p{margin:7px 0 0;color:#c9d8ea}
    main{max-width:1400px;margin:auto;padding:26px}.metrics{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:14px;margin-bottom:20px}
    .metric,.panel{background:var(--card);border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 4px 16px #17324d0b}.metric{padding:18px}.metric small{color:var(--muted)}.metric strong{display:block;font-size:29px;margin-top:6px}
    .panel{overflow:hidden}.toolbar{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:16px 18px;border-bottom:1px solid #e5e9f0}.toolbar h2{font-size:18px;margin:0}
    select,button{border:1px solid #cbd5e1;border-radius:8px;background:white;padding:8px 10px;font:inherit}button{cursor:pointer;background:var(--navy);color:white;border:0}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:13px 14px;border-bottom:1px solid #edf0f4;vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:#fafbfd}
    td{font-size:14px}.name{font-weight:700}.muted{color:var(--muted);font-size:12px}.pill{display:inline-block;border-radius:999px;padding:5px 9px;font-weight:700;font-size:11px;background:#eaf2ff;color:#155db8}
    .pill.review{background:#fff3d6;color:#9a6500}.pill.paid{background:#dff8ed;color:#067554}.pill.lost{background:#fde8e8;color:#a72e2e}
    a{color:var(--blue);font-weight:700;text-decoration:none}.empty{text-align:center;padding:50px;color:var(--muted)}
    @media(max-width:900px){.metrics{grid-template-columns:repeat(2,1fr)}.panel{overflow:auto}table{min-width:1050px}}@media(max-width:520px){.metrics{grid-template-columns:1fr 1fr}main{padding:14px}}
  </style>
</head>
<body>
  <header><h1>🚢 MEPT Lead Dashboard</h1><p>Leads → Package Choice → Payment Review → Conversion</p></header>
  <main>
    <section class="metrics">
      <div class="metric"><small>Total Leads</small><strong>{{ metrics.total }}</strong></div>
      <div class="metric"><small>Interested</small><strong>{{ metrics.interested }}</strong></div>
      <div class="metric"><small>Payment Review</small><strong>{{ metrics.review }}</strong></div>
      <div class="metric"><small>Paid Students</small><strong>{{ metrics.paid }}</strong></div>
      <div class="metric"><small>Conversion</small><strong>{{ metrics.conversion }}%</strong></div>
    </section>
    <section class="panel">
      <div class="toolbar"><h2>Student Leads</h2><span class="muted">Track Revenue, Leads, Conversion & Margin daily</span></div>
      {% if leads %}
      <table>
        <thead><tr><th>Lead</th><th>Phone</th><th>Class</th><th>Package / Fee</th><th>Status</th><th>Screenshot</th><th>Updated</th></tr></thead>
        <tbody>
        {% for lead in leads %}
          <tr>
            <td><div class="name">{{ lead.full_name or "Telegram User" }}</div><div class="muted">@{{ lead.telegram_username or "—" }} · {{ lead.chat_id }}</div></td>
            <td>{{ lead.phone or "Waiting" }}</td>
            <td>{{ lead.class_type or "Not selected" }}</td>
            <td>{{ lead.package or "—" }}{% if lead.fee %}<div class="muted">{{ "{:,}".format(lead.fee) }} MMK</div>{% endif %}</td>
            <td>
              <form method="post" action="{{ url_for('update_lead', chat_id=lead.chat_id) }}">
                <select name="status" onchange="this.form.submit()">
                  {% for option in statuses %}<option {% if lead.status == option %}selected{% endif %}>{{ option }}</option>{% endfor %}
                </select>
              </form>
            </td>
            <td>{% if lead.payment_file_id %}<a target="_blank" href="{{ url_for('payment_image', chat_id=lead.chat_id) }}">View payment</a>{% else %}<span class="muted">Waiting</span>{% endif %}</td>
            <td><span class="muted">{{ lead.updated_at.replace("T"," ")[:16] }}</span></td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}<div class="empty">No leads yet. New Telegram users will appear here automatically.</div>{% endif %}
    </section>
  </main>
</body>
</html>
"""


@app.get("/")
def health():
    return jsonify(status="ok", service="MEPT Student Support Bot")


@app.post("/telegram/<secret>")
def webhook(secret):
    if not secrets.compare_digest(secret, WEBHOOK_SECRET):
        abort(403)
    update = request.get_json(silent=True) or {}
    message = update.get("message", {})
    chat_id = upsert_identity(message)
    if chat_id is not None:
        if message.get("contact"):
            handle_contact(chat_id, message["contact"])
        elif message.get("photo"):
            handle_photo(chat_id, message["photo"])
        elif message.get("text"):
            handle_text(chat_id, message["text"])
    return jsonify(ok=True)


@app.get("/dashboard")
@require_dashboard_auth
def dashboard():
    with db() as connection:
        leads = connection.execute(
            "SELECT * FROM leads ORDER BY updated_at DESC"
        ).fetchall()
    total = len(leads)
    paid = sum(lead["status"] == "Paid" for lead in leads)
    metrics = {
        "total": total,
        "interested": sum(
            lead["status"] in ("Interested", "Payment Started") for lead in leads
        ),
        "review": sum(lead["status"] == "Payment Review" for lead in leads),
        "paid": paid,
        "conversion": round((paid / total * 100), 1) if total else 0,
    }
    return render_template_string(
        DASHBOARD_HTML,
        leads=leads,
        metrics=metrics,
        statuses=["New", "Interested", "Payment Started", "Payment Review", "Paid", "Lost"],
    )


@app.post("/dashboard/lead/<int:chat_id>")
@require_dashboard_auth
def update_lead(chat_id):
    status = request.form.get("status")
    allowed = {"New", "Interested", "Payment Started", "Payment Review", "Paid", "Lost"}
    if status not in allowed:
        abort(400)
    with db() as connection:
        connection.execute(
            "UPDATE leads SET status=?, updated_at=? WHERE chat_id=?",
            (status, now(), chat_id),
        )
    return redirect(url_for("dashboard"))


@app.get("/dashboard/payment/<int:chat_id>")
@require_dashboard_auth
def payment_image(chat_id):
    with db() as connection:
        lead = connection.execute(
            "SELECT payment_file_id FROM leads WHERE chat_id=?", (chat_id,)
        ).fetchone()
    if not lead or not lead["payment_file_id"]:
        abort(404)
    file_info = telegram("getFile", {"file_id": lead["payment_file_id"]})
    file_path = file_info.get("result", {}).get("file_path")
    if not file_path:
        abort(404)
    with urllib.request.urlopen(
        f"https://api.telegram.org/file/bot{TOKEN}/{file_path}", timeout=20
    ) as response:
        content = response.read()
        content_type = response.headers.get_content_type()
    return Response(content, content_type=content_type)


init_db()

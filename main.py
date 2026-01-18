import asyncio
import os
import nest_asyncio
import fitz  # PyMuPDF
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

nest_asyncio.apply()

# --- डमी सर्वर (Render Port Error के लिए) ---
def run_dummy_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is Running")
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

# --- कॉन्फ़िगरेशन ---
# Render Environment Variables में BOT_TOKEN डालें या यहाँ अपना टोकन लिखें
BOT_TOKEN = os.getenv("BOT_TOKEN", "7936101320:AAGTHSCteVyYUzPb-snNWXDn9MxQDZUXs1M")
browser_instance = None
playwright_instance = None

# --- PDF विश्लेषण लॉजिक ---
def extract_student_info(pdf_path):
    info = {
        "name": "Not Found", "father": "Not Found", "mother": "Not Found",
        "email": "Not Found", "abc_id": "Not Found", "roll": "Not Found",
        "college": "Not Found", "center": "Not Found"
    }
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()

        roll_match = re.search(r"Roll no is\s+([\w\d]+)", text)
        if roll_match: info["roll"] = roll_match.group(1).strip()

        name_match = re.search(r"NAME OF CANDIDATE\s*:\s*(.*)", text)
        if name_match: info["name"] = name_match.group(1).split('\n')[0].strip()

        father_match = re.search(r"FATHER'S NAME\s*:\s*(.*)", text)
        if father_match: info["father"] = father_match.group(1).split('\n')[0].strip()

        mother_match = re.search(r"MOTHER'S NAME\s*:\s*(.*)", text)
        if mother_match: info["mother"] = mother_match.group(1).split('\n')[0].strip()

        email_match = re.search(r"EMAIL ID\s*:\s*(.*)", text)
        if email_match: info["email"] = email_match.group(1).split('\n')[0].strip()

        abc_match = re.search(r"ABC ID\s*:\s*(\d+)", text)
        if abc_match: info["abc_id"] = abc_match.group(1).strip()
            
        college_match = re.search(r"COLLEGE NAME\s*:\s*(.*)", text)
        if college_match: info["college"] = college_match.group(1).split('\n')[0].strip()

        center_pattern = r"Exam Centre is\s*(.*?)(?=Print Date|To,|The Centre|NAME OF EXAMINATION)"
        center_match = re.search(center_pattern, text, re.DOTALL)
        if center_match: info["center"] = " ".join(center_match.group(1).split())

        doc.close()
        return info
    except Exception as e:
        print(f"Extraction Error: {e}")
        return info

# --- ब्राउज़र मैनेजमेंट ---
async def get_browser():
    global browser_instance, playwright_instance
    if browser_instance is None:
        playwright_instance = await async_playwright().start()
        # Render/Docker के लिए sandbox डिसेबल करना ज़रूरी है
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
    return browser_instance

# --- डाउनलोड लॉजिक ---
async def download_jnvu_pdf(form_number):
    pdf_path = f"admit_card_{form_number}.pdf"
    browser = await get_browser()
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    
    await page.route("**/*.{png,jpg,jpeg,gif,css,woff2}", lambda route: route.abort())
    url = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"
    
    try:
        await page.goto(url, wait_until="commit", timeout=30000)
        await page.fill("#txtchallanNo", str(form_number))
        submit_btn = page.locator("#btnGetResult")
        
        async with page.expect_download(timeout=20000) as download_info:
            await submit_btn.click()
            await asyncio.sleep(0.5) 
            if await submit_btn.is_visible():
                await submit_btn.click()
        
        download = await download_info.value
        await download.save_as(pdf_path)
        await context.close()
        return pdf_path
    except Exception as e:
        print(f"Download Error: {e}")
        await context.close()
        return None

# --- टेलीग्राम मैसेज हैंडलर ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("❌ कृपया केवल **Form Number** भेजें।")
        return

    status_msg = await update.message.reply_text("⚡ एडमिट कार्ड लोड हो रहा है...")
    file_path = await download_jnvu_pdf(user_input)

    if file_path and os.path.exists(file_path):
        data = extract_student_info(file_path)
        caption = (
            f"✅ **Admit Card Found!**\n\n"
            f"👤 **Name:** `{data['name']}`\n"
            f"👨‍💼 **Father:** `{data['father']}`\n"
            f"🎓 **College:** `{data['college']}`\n"
            f"🏫 **Center:**\n`{data['center']}`\n\n"
            f"📝 **Form No:** `{user_input}`"
        )
        try:
            with open(file_path, 'rb') as doc:
                await update.message.reply_document(document=doc, caption=caption, parse_mode='Markdown')
            os.remove(file_path)
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ फाइल भेजने में त्रुटि: {e}")
    else:
        await status_msg.edit_text("❌ एडमिट कार्ड नहीं मिला। कृपया Form Number सही से चेक करें।")

async def main():
    # डमी सर्वर को अलग थ्रेड में चालू करें
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("नमस्ते! अपना Form Number भेजें।")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ बॉट लाइव है...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        await download.save_as(pdf_path)
        await context.close()
        return pdf_path
    except Exception as e:
        print(f"Detailed Error: {e}")
        await context.close()
        return None

# --- मैसेज हैंडलर ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("❌ कृपया सही Form Number भेजें।")
        return

    status = await update.message.reply_text("⏳ वेबसाइट से एडमिट कार्ड निकाला जा रहा है, कृपया 1 मिनट इंतज़ार करें...")
    
    try:
        file_path = await download_jnvu_pdf(user_input)

        if file_path and os.path.exists(file_path):
            data = extract_student_info(file_path)
            caption = f"✅ **Admit Card Found!**\n\n👤 **Name:** `{data['name']}`\n🏫 **Center:** `{data['center']}`"
            
            with open(file_path, 'rb') as doc:
                await update.message.reply_document(document=doc, caption=caption, parse_mode='Markdown')
            
            os.remove(file_path)
            await status.delete()
        else:
            await status.edit_text("❌ एडमिट कार्ड नहीं मिला। वेबसाइट धीमी हो सकती है या Form Number गलत है।")
    except Exception as e:
        await status.edit_text(f"⚠️ एरर: {str(e)}")

async def main():
    if not BOT_TOKEN:
        return
    
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("अपना Form Number भेजें।")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
        await status.delete()
    else:
        await status.edit_text("❌ एडमिट कार्ड नहीं मिला।")

async def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing!")
        return
        
    # डमी सर्वर को अलग धागे (Thread) में शुरू करें
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("नमस्ते! अपना Form Number भेजें।")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("✅ बॉट और डमी सर्वर लाइव हैं...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("❌ कृपया केवल Form Number भेजें।")
        return

    status = await update.message.reply_text("⏳ एडमिट कार्ड ढूँढा जा रहा है...")
    file_path = await download_jnvu_pdf(user_input)

    if file_path and os.path.exists(file_path):
        data = extract_student_info(file_path)
        caption = f"✅ **Admit Card Found**\n👤 Name: `{data['name']}`\n🏫 Center: `{data['center']}`"
        await update.message.reply_document(document=open(file_path, 'rb'), caption=caption, parse_mode='Markdown')
        os.remove(file_path)
    else:
        await status.edit_text("❌ नहीं मिला।")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Form Number भेजें।")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())


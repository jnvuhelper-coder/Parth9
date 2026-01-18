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

# --- डमी सर्वर ---
def run_dummy_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is active!")
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

# --- PDF से जानकारी निकालने का फंक्शन ---
def extract_student_info(pdf_path):
    info = {"name": "Not Found", "center": "Not Found"}
    try:
        doc = fitz.open(pdf_path)
        text = "".join([page.get_text() for page in doc])
        
        name_match = re.search(r"NAME OF CANDIDATE\s*:\s*(.*)", text)
        if name_match: info["name"] = name_match.group(1).split('\n')[0].strip()

        center_pattern = r"Exam Centre is\s*(.*?)(?=Print Date|To,|The Centre|NAME OF EXAMINATION)"
        center_match = re.search(center_pattern, text, re.DOTALL)
        if center_match: info["center"] = " ".join(center_match.group(1).split())
        
        doc.close()
    except:
        pass
    return info

# --- ब्राउज़र और डाउनलोड लॉजिक ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
browser_instance = None
playwright_instance = None

async def get_browser():
    global browser_instance, playwright_instance
    if browser_instance is None:
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
    return browser_instance

async def download_jnvu_pdf(form_number):
    pdf_path = f"admit_card_{form_number}.pdf"
    browser = await get_browser()
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    
    # JNVU वेबसाइट कई बार धीमी होती है, इसलिए timeout बढ़ाया गया है
    url = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"
    
    try:
        await page.goto(url, wait_until="load", timeout=90000)
        await page.fill("#txtchallanNo", str(form_number))
        
        # बटन पर क्लिक करने के बाद डाउनलोड का इंतज़ार
        async with page.expect_download(timeout=60000) as download_info:
            await page.click("#btnGetResult")
        
        download = await download_info.value
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


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

# --- डमी सर्वर (Render की Port Error ठीक करने के लिए) ---
def run_dummy_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is active and running!")

    # Render अपने आप PORT एनवायरनमेंट वेरिएबल देता है
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Dummy server started on port {port}")
    server.serve_forever()

# --- एडमिट कार्ड लॉजिक (पुराना वाला ही है) ---
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
    url = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.fill("#txtchallanNo", str(form_number))
        async with page.expect_download(timeout=30000) as download_info:
            await page.click("#btnGetResult")
        download = await download_info.value
        await download.save_as(pdf_path)
        await context.close()
        return pdf_path
    except Exception as e:
        print(f"Download Error: {e}")
        await context.close()
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("❌ कृपया केवल Form Number भेजें।")
        return

    status = await update.message.reply_text("⏳ एडमिट कार्ड लोड हो रहा है...")
    file_path = await download_jnvu_pdf(user_input)

    if file_path and os.path.exists(file_path):
        # यहाँ आप चाहें तो PDF से डेटा निकालने वाला फंक्शन डाल सकते हैं
        await update.message.reply_document(document=open(file_path, 'rb'), caption="✅ एडमिट कार्ड मिल गया!")
        os.remove(file_path)
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


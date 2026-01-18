import asyncio
import os
import nest_asyncio
import fitz  # PyMuPDF
import re
import threading
from fastapi import FastAPI
import uvicorn
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

nest_asyncio.apply()

# --- FastAPI सर्वर सेटअप ---
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Bot is running", "server": "FastAPI"}

def run_fastapi():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- कॉन्फ़िगरेशन ---
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
        text = "".join([page.get_text() for page in doc])
        
        roll_match = re.search(r"Roll no is\s+([\w\d]+)", text)
        if roll_match: info["roll"] = roll_match.group(1).strip()

        name_match = re.search(r"NAME OF CANDIDATE\s*:\s*(.*)", text)
        if name_match: info["name"] = name_match.group(1).split('\n')[0].strip()

        father_match = re.search(r"FATHER'S NAME\s*:\s*(.*)", text)
        if father_match: info["father"] = father_match.group(1).split('\n')[0].strip()

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
    
    url = "https://erp.jnvuiums.in/(S(biolzjtwlrcfmzwwzgs5uj5n))/Exam/Pre_Exam/Exam_ForALL_AdmitCard.aspx#"
    
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        await page.fill("#txtchallanNo", str(form_number))
        submit_btn = page.locator("#btnGetResult")
        
        async with page.expect_download(timeout=30000) as download_info:
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
        await update.message.reply_text("❌ कृपया केवल Form Number भेजें।")
        return

    status_msg = await update.message.reply_text("⚡ एडमिट कार्ड लोड हो रहा है...")
    file_path = await download_jnvu_pdf(user_input)

    if file_path and os.path.exists(file_path):
        data = extract_student_info(file_path)
        caption = (
            f"✅ **Admit Card Found!**\n\n"
            f"👤 **Name:** `{data['name']}`\n"
            f"👨‍💼 **Father:** `{data['father']}`\n"
            f"🏫 **Center:**\n`{data['center']}`"
        )
        try:
            with open(file_path, 'rb') as doc:
                await update.message.reply_document(document=doc, caption=caption, parse_mode='Markdown')
            os.remove(file_path)
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ त्रुटि: {e}")
    else:
        await status_msg.edit_text("❌ एडमिट कार्ड नहीं मिला।")

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("अपना Form Number भेजें।")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    await app.initialize()
    await app.start_polling()
    print("✅ Telegram Bot Started")

if __name__ == "__main__":
    # FastAPI को अलग थ्रेड में चलाएं
    threading.Thread(target=run_fastapi, daemon=True).start()
    
    # बॉट को मुख्य लूप में चलाएं
    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    loop.run_forever()

import asyncio
import os
import nest_asyncio
import fitz  # PyMuPDF
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

nest_asyncio.apply()

# Environment Variable से टोकन लेना (Render के लिए सुरक्षित)
BOT_TOKEN = os.getenv("BOT_TOKEN")
browser_instance = None
playwright_instance = None

def extract_student_info(pdf_path):
    info = {"name": "Not Found", "father": "Not Found", "mother": "Not Found", 
            "email": "Not Found", "abc_id": "Not Found", "roll": "Not Found", 
            "college": "Not Found", "center": "Not Found"}
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
    except Exception:
        return info

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
        print(f"Error: {e}")
        await context.close()
        return None

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


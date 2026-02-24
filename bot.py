import requests, json, os, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8335639637:AAHTscVr7KAAzNfs09Nbnr154GxpBDEO5rg"
ADMIN_ID = 7691071175
PANEL_API_KEY = "144db1b838d2e6f5fb04c07a12535438"
PANEL_API_URL = "https://smmziox.store/api/v2"
UPI_ID = "zioxrohit@fam"
PER_PAGE = 6
USERS_FILE = "users.json"

# ---------------- STORAGE ----------------
USERS = {}
SERVICE_CACHE = {}
ORDER_FLOW = {}
BALANCE_FLOW = {}
STATUS_FLOW = {}
CANCEL_FLOW = {}

# ---------------- PERSISTENT STORAGE ----------------
def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(USERS, f)

def load_users():
    global USERS
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            try:
                USERS = json.load(f)
            except:
                USERS = {}

# ---------------- PANEL API ----------------
def panel_request(data):
    data["key"] = PANEL_API_KEY
    try:
        res = requests.post(PANEL_API_URL, data=data, timeout=20)
        return res.json()
    except:
        return {}

def load_services():
    SERVICE_CACHE.clear()
    res = panel_request({"action": "services"})
    for s in res if isinstance(res, list) else []:
        SERVICE_CACHE[int(s["service"])] = s

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    USERS.setdefault(uid, {"balance": 0})
    save_users()
    await update.message.reply_text("ℹ️ Bot updated ✅")  # notify user of update
    kb = [
        [InlineKeyboardButton("🛒 Order", callback_data="order")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("💳 Balance", callback_data="balance")]
    ]
    await update.message.reply_text(
        "🤖 Welcome\nUse buttons or commands",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ---------------- HELP ----------------
async def help_cmd(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Help Menu*\n\n"
        "/start – Start bot\n"
        "/service – Show services\n"
        "/add – Add balance\n"
        "/balance – Check balance\n"
        "/status – Check order status\n"
        "/cancel – Cancel order\n\n"
        "Use buttons also 👇",
        parse_mode="Markdown"
    )

# ---------------- COMMAND SHORTCUTS ----------------
async def service_cmd(update, context):
    load_services()  # always fetch latest before showing
    await show_services(update, context, 0)

async def add_cmd(update, context):
    uid = str(update.effective_user.id)
    BALANCE_FLOW[uid] = {}
    await update.message.reply_text("💰 Enter amount (min ₹10):")

async def balance_cmd(update, context):
    uid = str(update.effective_user.id)
    bal = USERS.get(uid, {}).get("balance", 0)
    await update.message.reply_text(f"💳 Balance: ₹{bal}")

# ---------------- SERVICE LIST ----------------
async def show_services(update, context, page=0):
    load_services()  # always fetch latest
    services = list(SERVICE_CACHE.values())
    start_idx = page * PER_PAGE
    end_idx = start_idx + PER_PAGE
    text = "🛒 *Select Service*\n\n"
    buttons = []
    for i, s in enumerate(services[start_idx:end_idx], start=start_idx + 1):
        text += f"Order {i}\n{s['name']}\n₹{s['rate']} / {s['min']}-{s['max']}\n\n"
        buttons.append([InlineKeyboardButton(f"Order {s['service']}", callback_data=f"select_{s['service']}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))
    if end_idx < len(services): nav.append(InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))
    if nav: buttons.append(nav)
    if update.callback_query:
        try: await update.callback_query.answer()
        except: pass
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ---------------- CALLBACKS ----------------
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    data = q.data
    uid = str(q.from_user.id)

    if data == "order":
        load_services()
        await show_services(update, context, 0)
    elif data.startswith("page_"):
        await show_services(update, context, int(data.split("_")[1]))
    elif data.startswith("select_"):
        ORDER_FLOW[uid] = {"service": int(data.split("_")[1])}
        await q.message.reply_text("📦 Enter quantity:")
    elif data == "add_balance":
        BALANCE_FLOW[uid] = {}
        await q.message.reply_text("💰 Enter amount (min ₹10):")
    elif data == "balance":
        await q.message.reply_text(f"💳 Balance: {USERS.get(uid,{}).get('balance',0)}")
    elif data.startswith("cancel_yes_"):
        order_id = data.split("_")[2]
        uid = str(data.split("_")[3])
        res = panel_request({"action": "cancel", "order": order_id})
        if res.get("status") == "Canceled":
            refund = float(res.get("charge",0))
            USERS.setdefault(uid, {"balance":0})
            USERS[uid]["balance"] += refund
            save_users()
            await q.message.edit_text(f"✅ Order canceled\n💰 Refund ₹{refund}")
        else:
            await q.message.edit_text("❌ Cannot cancel this order")
        CANCEL_FLOW.pop(uid, None)
    elif data.startswith("cancel_no_"):
        order_id = data.split("_")[2]
        uid = str(data.split("_")[3])
        await q.message.edit_text("❌ Cancellation aborted")
        CANCEL_FLOW.pop(uid, None)

# ---------------- MESSAGE ROUTER ----------------
async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip() if update.message.text else None
    if not text: return

    # STATUS
    if uid in STATUS_FLOW:
        res = panel_request({"action":"status","order":text})
        await update.message.reply_text(f"📦 Status: {res.get('status','Unknown')}")
        STATUS_FLOW.pop(uid)
        return

    # CANCEL
    if uid in CANCEL_FLOW:
        res = panel_request({"action":"status","order":text})
        status = res.get("status")
        if status in ["Canceled","Completed",None]:
            await update.message.reply_text("❌ Order cannot be canceled")
            CANCEL_FLOW.pop(uid)
            return
        kb = [[
            InlineKeyboardButton("✅ Yes", callback_data=f"cancel_yes_{text}_{uid}"),
            InlineKeyboardButton("❌ No", callback_data=f"cancel_no_{text}_{uid}")
        ]]
        await update.message.reply_text(f"❌ Cancel available for Order ID {text}?\nChoose:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ORDER FLOW
    if uid in ORDER_FLOW:
        flow = ORDER_FLOW[uid]
        USERS.setdefault(uid, {"balance":0})
        service = SERVICE_CACHE.get(flow["service"])
        if not service:
            await update.message.reply_text("❌ Service no longer available, order canceled")
            ORDER_FLOW.pop(uid)
            return

        # STEP 1: Quantity
        if "quantity" not in flow:
            try:
                flow["quantity"] = int(text)
                await update.message.reply_text("🔗 Send link:")
            except:
                await update.message.reply_text("❌ Invalid quantity")
            return

        # STEP 2: Link → detect valid link before placing order
        if "link" not in flow:
            url_pattern = r'https?://\S+'
            if not re.search(url_pattern, text):
                await update.message.reply_text("❌ Invalid or missing link. Order not placed. Please try again with a valid link.")
                ORDER_FLOW.pop(uid)
                return

            flow["link"] = text
            cost = (float(service["rate"])/1000)*flow["quantity"]
            if USERS[uid]["balance"] < cost:
                await update.message.reply_text("❌ Insufficient balance")
                ORDER_FLOW.pop(uid)
                return

            msg = await update.message.reply_text("⏳ Placing your order...")
            res = panel_request({
                "action":"add",
                "service":flow["service"],
                "quantity":flow["quantity"],
                "link":flow["link"]
            })
            if res.get("order"):
                USERS[uid]["balance"] -= cost
                save_users()
                await msg.edit_text(f"✅ *Order Placed*\n🆔 Order ID: `{res.get('order')}`", parse_mode="Markdown")
            else:
                await msg.edit_text(f"❌ Order failed. Possibly invalid link or service.\n{res}")
            ORDER_FLOW.pop(uid)
            return

    # BALANCE FLOW
    if uid in BALANCE_FLOW:
        flow = BALANCE_FLOW[uid]
        if "amount" not in flow:
            try:
                amt = int(text)
                if amt < 10:
                    await update.message.reply_text("❌ Minimum ₹10")
                    return
                flow["amount"] = amt
                flow["waiting_ss"] = True
                await update.message.reply_text(
                    f"💳 Pay ₹{amt} to `{UPI_ID}`\n📸 Send screenshot after payment",
                    parse_mode="Markdown"
                )
            except:
                await update.message.reply_text("❌ Enter valid amount")
            return
        elif flow.get("waiting_ss", False):
            await update.message.reply_text("📸 Please send screenshot after payment")
            return

# ---------------- SCREENSHOT ----------------
async def payment_screenshot(update: Update, context):
    uid = str(update.effective_user.id)
    if uid not in BALANCE_FLOW: return
    flow = BALANCE_FLOW[uid]
    flow["ss"] = update.message.photo[-1].file_id
    flow["waiting_ss"] = False
    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok_{uid}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{uid}")
    ]]
    await context.bot.send_photo(ADMIN_ID, photo=flow["ss"],
        caption=f"User: {uid}\nAmount: ₹{flow['amount']}",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text("⏳ Screenshot sent to admin for approval")

# ---------------- ADMIN ACTION ----------------
async def payment_decision(update: Update, context):
    q = update.callback_query
    try: await q.answer()
    except: pass
    _, action, uid = q.data.split("_")
    uid = str(uid)
    flow = BALANCE_FLOW.pop(uid, None)
    if not flow: return
    USERS.setdefault(uid, {"balance":0})
    if action=="ok":
        USERS[uid]["balance"] += flow["amount"]
        save_users()
        await context.bot.send_message(uid, f"✅ ₹{flow['amount']} added successfully")
    else:
        await context.bot.send_message(uid, "❌ Payment rejected")

# ---------------- STATUS / CANCEL COMMANDS ----------------
async def status_cmd(update, context):
    STATUS_FLOW[str(update.effective_user.id)] = True
    await update.message.reply_text("📦 Send Order ID to check status")

async def cancel_cmd(update, context):
    uid = str(update.effective_user.id)
    CANCEL_FLOW[uid] = True
    await update.message.reply_text("❌ Send Order ID to cancel")

# ---------------- SET COMMANDS ----------------
async def set_bot_commands(app):
    commands = [
        BotCommand("start","Start bot"),
        BotCommand("help","Help menu"),
        BotCommand("service","Show services"),
        BotCommand("add","Add balance"),
        BotCommand("balance","Check balance"),
        BotCommand("status","Check order status"),
        BotCommand("cancel","Cancel order"),
    ]
    await app.bot.set_my_commands(commands)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    load_users()
    load_services()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("service", service_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Callback queries
    app.add_handler(CallbackQueryHandler(payment_decision, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(callbacks))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, payment_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    import asyncio
    asyncio.get_event_loop().run_until_complete(set_bot_commands(app))

    print("🤖 Bot running...")
    app.run_polling()
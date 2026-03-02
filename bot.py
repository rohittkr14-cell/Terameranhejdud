import requests
import json
import os
import re
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = "7962798509:AAFSZrMZmS_h967X03AH_ZzlSUjFYG6TmQM"
ADMIN_ID = 7691071175
PANEL_API_KEY = "b995856bd13c1a539b857b8dd36e2b92"
PANEL_API_URL = "https://smmziox.store/api/v2"
UPI_ID = "zioxrohit@fam"
PER_PAGE = 10

# Storage files
USERS_FILE = "users.json"
ORDER_HISTORY_FILE = "order_history.json"
REFUND_HISTORY_FILE = "refund_history.json"

# Global variables
USERS = {}
SERVICE_CACHE = {}
ORDER_FLOW = {}
BALANCE_FLOW = {}
STATUS_FLOW = {}
CANCEL_FLOW = {}
REFUND_FLOW = {}
PENDING_REFUNDS = {}
ORDER_HISTORY = {}
REFUND_HISTORY = {}
ADMIN_FLOW = {}

def save_users():
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f)
    except:
        pass

def save_order_history():
    try:
        with open(ORDER_HISTORY_FILE, "w") as f:
            json.dump(ORDER_HISTORY, f)
    except:
        pass

def save_refund_history():
    try:
        with open(REFUND_HISTORY_FILE, "w") as f:
            json.dump(REFUND_HISTORY, f)
    except:
        pass

def load_users():
    global USERS
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f:
                USERS = json.load(f)
    except:
        USERS = {}

def load_order_history():
    global ORDER_HISTORY
    try:
        if os.path.exists(ORDER_HISTORY_FILE):
            with open(ORDER_HISTORY_FILE, "r") as f:
                ORDER_HISTORY = json.load(f)
    except:
        ORDER_HISTORY = {}

def load_refund_history():
    global REFUND_HISTORY
    try:
        if os.path.exists(REFUND_HISTORY_FILE):
            with open(REFUND_HISTORY_FILE, "r") as f:
                REFUND_HISTORY = json.load(f)
    except:
        REFUND_HISTORY = {}

def panel_request(data):
    data["key"] = PANEL_API_KEY
    try:
        res = requests.post(PANEL_API_URL, data=data, timeout=5, headers={'Connection': 'close'})
        return res.json()
    except:
        return {}

def load_services_fast():
    if SERVICE_CACHE:
        return list(SERVICE_CACHE.values())
    SERVICE_CACHE.clear()
    res = panel_request({"action": "services"})
    if isinstance(res, list):
        for s in res:
            try:
                SERVICE_CACHE[int(s["service"])] = s
            except:
                pass
    return list(SERVICE_CACHE.values())

async def send_refund_request_to_admin(context, uid, order_id):
    res = panel_request({"action": "status", "order": order_id})
    panel_status = res.get("status", "Unknown")
    
    if panel_status != "Canceled":
        return f"❌ Order status: `{panel_status}`\nMust be `Canceled` for refund"
    
    if order_id not in ORDER_HISTORY:
        return "❌ Order not found contact support "
    
    if order_id in REFUND_HISTORY:
        return "❌ Already refunded"
    
    order_info = ORDER_HISTORY[order_id]
    refund_amount = order_info["amount"]
    
    PENDING_REFUNDS[order_id] = {
        "user_id": uid,
        "amount": refund_amount,
        "panel_status": panel_status,
        "order_info": order_info
    }
    
    kb = [
        [InlineKeyboardButton("✅ APPROVE", callback_data=f"refund_ok_{order_id}_{uid}")],
        [InlineKeyboardButton("❌ REJECT", callback_data=f"refund_no_{order_id}_{uid}")]
    ]
    
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💰 *REFUND REQUEST*\n\n👤 `{uid}`\n🆔 `{order_id}`\n💵 ₹{refund_amount:.2f}\n📦 {order_info['service']}\n🔢 {order_info['quantity']}",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    except:
        pass
    
    return f"✅ Refund request sent\n🆔 `{order_id}`\n💰 ₹{refund_amount:.2f}"

async def approve_refund(user_uid, order_id):
    if order_id not in PENDING_REFUNDS:
        return "❌ Invalid request"
    
    pending = PENDING_REFUNDS.pop(order_id)
    user_uid = pending["user_id"]
    refund_amount = pending["amount"]
    
    USERS.setdefault(user_uid, {"balance": 0})
    USERS[user_uid]["balance"] += refund_amount
    save_users()
    
    REFUND_HISTORY[order_id] = {
        "user_id": user_uid,
        "amount": refund_amount,
        "timestamp": str(asyncio.get_event_loop().time())
    }
    save_refund_history()
    
    return f"✅ *Refund Added*\n🆔 `{order_id}`\n💰 ₹{refund_amount:.2f}"

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if int(uid) != ADMIN_ID:
        return
    
    ADMIN_FLOW[uid] = "main"
    kb = [
        [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Balance", callback_data="admin_balance")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📦 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("🔙 Close", callback_data="admin_close")]
    ]
    await update.message.reply_text(
        "🔧 *ADMIN PANEL*\n\n👥 Users\n💰 Update balance\n📢 Broadcast\n📦 Orders\n🔙 Close",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = str(q.from_user.id)
    
    if int(uid) != ADMIN_ID:
        await q.answer("❌ Unauthorized")
        return
    
    if data == "admin_orders":
        total_orders = len(ORDER_HISTORY)
        total_revenue = sum(info["amount"] for info in ORDER_HISTORY.values())
        text = f"📦 *ORDERS ({total_orders})*\n💰 *Revenue: ₹{total_revenue:.2f}*"
        await q.edit_message_text(text, parse_mode="Markdown")
        ADMIN_FLOW[uid] = "orders"
        return
        
    if data == "admin_users":
        total_users = len(USERS)
        total_balance = sum(data.get("balance", 0) for data in USERS.values())
        text = f"👥 *USERS ({total_users})*\n💰 *Balance: ₹{total_balance:.2f}*"
        await q.edit_message_text(text, parse_mode="Markdown")
        ADMIN_FLOW[uid] = "users"
        return
        
    if data == "admin_balance":
        ADMIN_FLOW[uid] = "balance"
        await q.edit_message_text("💰 *UPDATE BALANCE*\n\n`user_id amount`\n\nExample: `7691071175 1000`", parse_mode="Markdown")
        return
    
    if data == "admin_broadcast":
        ADMIN_FLOW[uid] = "broadcast"
        await q.edit_message_text(f"📢 *BROADCAST*\n\n📊 Users: {len(USERS)}\n\nSend message:", parse_mode="Markdown")
        return
        
    if data == "admin_close":
        ADMIN_FLOW.pop(uid, None)
        await q.message.delete()
        return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    USERS.setdefault(uid, {"balance": 0})
    save_users()
    kb = [
        [InlineKeyboardButton("🛒 Order", callback_data="order")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("💳 Balance", callback_data="balance")]
    ]
    await update.message.reply_text(
        "🤖 Welcome\nUse buttons or /commands",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def help_cmd(update, context):
    await update.message.reply_text(
         "📖 Help........... 1. Menu /start – Start bot 2. /service – Show services 3. /add – Add balance 4. /balance – Check balance 5. /status – Check order status 6. /cancel – Cancel order ........... Use commands 👇"
    )

async def service_cmd(update, context):
    services = load_services_fast()
    if not services:
        await update.message.reply_text("❌ No services")
        return
    await show_services(update, context, 0)

async def add_cmd(update, context):
    uid = str(update.effective_user.id)
    BALANCE_FLOW[uid] = {}
    await update.message.reply_text("💰 Enter amount to add (min ₹10):")

async def balance_cmd(update, context):
    uid = str(update.effective_user.id)
    bal = USERS.get(uid, {}).get("balance", 0)
    await update.message.reply_text(f"💳 Balance: ₹{bal}")

async def refund_cmd(update, context):
    uid = str(update.effective_user.id)
    REFUND_FLOW[uid] = True
    await update.message.reply_text("💰 Send Order ID for refund")

async def cancel_cmd(update, context):
    uid = str(update.effective_user.id)
    CANCEL_FLOW[uid] = True
    await update.message.reply_text("❌ Send Order ID to cancel")

async def status_cmd(update, context):
    STATUS_FLOW[str(update.effective_user.id)] = True
    await update.message.reply_text("📦 Send Order ID")

async def show_services(update, context, page=0):
    services = load_services_fast()
    if not services:
        if update.callback_query:
            await update.callback_query.message.edit_text("❌ No services")
        else:
            await update.message.reply_text("❌ No services")
        return
    
    start_idx = page * PER_PAGE
    end_idx = min(start_idx + PER_PAGE, len(services))
    text = f"🛒 Services ({len(services)}):\n\n"
    
    buttons = []
    for i, service in enumerate(services[start_idx:end_idx], start=start_idx + 1):
        rate = service.get('rate', 0)
        text += f"{i}. {service['name']}\n💰 ₹{rate}/1000\n\n"
        buttons.append([InlineKeyboardButton(f"Order {i}", callback_data=f"select_{service['service']}")])
    
    if page > 0:
        buttons.append([InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}")])
    if end_idx < len(services):
        buttons.append([InlineKeyboardButton("➡️ Next", callback_data=f"page_{page+1}")])
    
    buttons.append([InlineKeyboardButton("🔙 Menu", callback_data="main_menu")])
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = str(q.from_user.id)

    if data.startswith("refund_ok_"):
        parts = data.split("_")
        order_id = parts[2]
        user_uid = parts[3]
        result = await approve_refund(user_uid, order_id)
        await q.edit_message_text(result, parse_mode="Markdown")
        return
    
    if data.startswith("refund_no_"):
        parts = data.split("_")
        order_id = parts[2]
        user_uid = parts[3]
        PENDING_REFUNDS.pop(order_id, None)
        await q.edit_message_text(f"❌ Refund Rejected\n🆔 `{order_id}`", parse_mode="Markdown")
        return

    if data.startswith("admin_"):
        await admin_callbacks(update, context)
        return

    if data == "order" or data == "main_menu":
        services = load_services_fast()
        if services:
            await show_services(update, context, 0)
        else:
            await q.message.edit_text("❌ No services")
        return
    
    if data.startswith("page_"):
        page = int(data.split("_")[1])
        await show_services(update, context, page)
        return
    
    if data.startswith("select_"):
        service_id = int(data.split("_")[1])
        service = SERVICE_CACHE.get(service_id)
        if service:
            ORDER_FLOW[uid] = {"service": service_id, "service_info": service, "step": "quantity"}
            await q.message.reply_text(f"📦 Enter quantity\nMin: {service.get('min', 0)}")
        return
    
    if data == "add_balance":
        BALANCE_FLOW[uid] = {}
        await q.message.reply_text("💰 Enter amount to add  (min ₹10):")
        return
    
    if data == "balance":
        bal = USERS.get(uid, {}).get("balance", 0)
        await q.message.edit_text(f"💳 Balance: ₹{bal}")
        return

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()
    
    if uid in CANCEL_FLOW:
        res = panel_request({"action": "cancel", "order": text})
        status = res.get("status", "Unknown")
        if status == "Canceled":
            await update.message.reply_text(f"✅ `{text}` canceled")
        else:
            await update.message.reply_text(f"❌ Cancel failed: `{status}`")
        CANCEL_FLOW.pop(uid, None)
        return
    
    if int(uid) == ADMIN_ID and uid in ADMIN_FLOW:
        if ADMIN_FLOW[uid] == "balance":
            try:
                parts = text.split()
                target_uid = parts[0]
                amount = float(parts[1])
                USERS.setdefault(target_uid, {"balance": 0})
                USERS[target_uid]["balance"] += amount
                save_users()
                await update.message.reply_text(f"✅ Added ₹{amount} to `{target_uid}`")
                ADMIN_FLOW[uid] = "main"
            except:
                await update.message.reply_text("❌ `user_id amount`")
            return
        
        if ADMIN_FLOW[uid] == "broadcast":
            success = 0
            for u_id in USERS:
                try:
                    await context.bot.send_message(int(u_id), f"📢 {text}")
                    success += 1
                    await asyncio.sleep(0.02)
                except:
                    pass
            await update.message.reply_text(f"✅ Broadcasted to {success} users")
            ADMIN_FLOW[uid] = "main"
            return

    if uid in REFUND_FLOW:
        result = await send_refund_request_to_admin(context, uid, text)
        await update.message.reply_text(result, parse_mode="Markdown")
        REFUND_FLOW.pop(uid, None)
        return

    if uid in STATUS_FLOW:
        res = panel_request({"action": "status", "order": text})
        await update.message.reply_text(f"📦 `{res.get('status', 'Unknown')}`", parse_mode="Markdown")
        STATUS_FLOW.pop(uid, None)
        return

    if uid in ORDER_FLOW:
        flow = ORDER_FLOW[uid]
        service = flow["service_info"]
        
        if flow["step"] == "quantity":
            try:
                qty = int(text)
                min_qty = int(service.get('min', 0))
                if qty < min_qty:
                    await update.message.reply_text(f"❌ Min: {min_qty}")
                    return
                flow["quantity"] = qty
                flow["step"] = "link"
                await update.message.reply_text("🔗 Enter link:")
                return
            except:
                await update.message.reply_text("❌ Number only")
                return
        
        if flow["step"] == "link":
            if not re.search(r'https?://', text):
                await update.message.reply_text("❌ Invalid link")
                return
            
            flow["link"] = text
            rate = float(service["rate"])
            cost = (rate / 1000) * flow["quantity"]
            
            if USERS.get(uid, {}).get("balance", 0) < cost:
                await update.message.reply_text("❌ Low balance")
                del ORDER_FLOW[uid]
                return
            
            msg = await update.message.reply_text("⏳ Placing order...")
            
            res = panel_request({
                "action": "add",
                "service": flow["service"],
                "quantity": flow["quantity"],
                "link": flow["link"]
            })
            
            USERS.setdefault(uid, {"balance": 0})
            USERS[uid]["balance"] -= cost
            save_users()
            
            if res.get("order"):
                order_id = res["order"]
                ORDER_HISTORY[order_id] = {
                    "user": uid,
                    "amount": cost,
                    "service": flow["service"],
                    "quantity": flow["quantity"],
                    "timestamp": str(asyncio.get_event_loop().time())
                }
                save_order_history()
                
                await msg.edit_text(
                    f"✅ *ORDER #{order_id}*\n📦 {service['name']}\n🔢 {flow['quantity']}\n💰 ₹{cost:.2f}\n📊 Processing...",
                    parse_mode="Markdown"
                )
            else:
                USERS[uid]["balance"] += cost
                save_users()
                await msg.edit_text("❌ Order failed")
            
            del ORDER_FLOW[uid]
            return

    if uid in BALANCE_FLOW:
        flow = BALANCE_FLOW[uid]
        try:
            amt = int(text)
            if amt < 10:
                await update.message.reply_text("❌ Min ₹10")
                return
            flow["amount"] = amt
            flow["waiting_ss"] = True
            await update.message.reply_text(f"💳 Pay ₹{amt} to upi -  `{UPI_ID}`\n📸 Send Screenshot", parse_mode="Markdown")
            return
        except:
            await update.message.reply_text("❌ Enter amount")
            return

async def payment_screenshot(update: Update, context):
    uid = str(update.effective_user.id)
    if uid not in BALANCE_FLOW:
        return
    flow = BALANCE_FLOW[uid]
    flow["ss"] = update.message.photo[-1].file_id
    flow["waiting_ss"] = False
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{uid}")]]
    try:
        await context.bot.send_photo(ADMIN_ID, photo=flow["ss"], caption=f"User: {uid}\n₹{flow['amount']}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ Add Money Request Sent to admin")
    except:
        pass

async def payment_decision(update: Update, context):
    q = update.callback_query
    data = q.data
    parts = data.split("_")
    action = parts[1]
    uid = parts[2]
    
    flow = BALANCE_FLOW.pop(uid, None)
    if not flow:
        return
    
    USERS.setdefault(uid, {"balance": 0})
    if action == "ok":
        USERS[uid]["balance"] += flow["amount"]
        save_users()
        await context.bot.send_message(uid, f"✅ ₹{flow['amount']} added")
    else:
        await context.bot.send_message(uid, "❌ Payment rejected")

async def set_bot_commands(app):
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("help", "Help"),
        BotCommand("service", "Services"),
        BotCommand("add", "Add balance"),
        BotCommand("balance", "Check balance"),
        BotCommand("status", "Check status"),
        BotCommand("cancel", "Cancel order"),
        BotCommand("refund", "Request refund"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except:
        pass

def main():
    load_users()
    load_order_history()
    load_refund_history()
    
    app = ApplicationBuilder().token(BOT_TOKEN).pool_timeout(10).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("service", service_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("refund", refund_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(payment_decision, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(callbacks))

    # Messages
    app.add_handler(MessageHandler(filters.PHOTO, payment_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))

    print("🚀 SMM BOT v2.5 STARTED")
    print("✅ Pyroid3 + AWS Ready")
    
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from api.chatgpt import ChatGPT
import os
import logging
import time
from threading import Timer
import traceback

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(access_token)
line_handler = WebhookHandler(channel_secret)

app = Flask(__name__)
chatgpt = ChatGPT()

# 用於暫存多張圖片的字典
pending_images = {}
BATCH_WAIT_TIME = 3  # 等待3秒收集所有圖片

# 歡迎訊息
WELCOME_MESSAGE = """📈 **股票分析機器人**

歡迎使用專業股票分析服務！

🔸 **使用方式：**
1️⃣ 輸入「問股市 [你的持股狀況]」
   例：問股市 持有台積電200股，成本600元

2️⃣ 傳送股票圖表截圖
   • 支援單張或多張圖片同時傳送
   • 立即進行分析並回復結果

💡 **多圖分析建議：**
   • 不同時間週期（日線、週線、月線）
   • 不同技術指標圖表
   • 個股與大盤對比圖

🔸 **其他指令：**
• 更新持股 [新資訊] - 更新投資組合
• help - 顯示說明
"""

def process_batch_images(user_id):
    """處理批次圖片分析"""
    logger.info(f"🔄 Timer triggered for user {user_id}")
    
    try:
        if user_id not in pending_images:
            logger.error(f"❌ No pending_images entry for user {user_id}")
            return
            
        if not pending_images[user_id]['images']:
            logger.error(f"❌ No images in pending_images for user {user_id}")
            return
        
        user_data = pending_images[user_id]
        images = user_data['images']
        
        logger.info(f"📊 Processing {len(images)} images for user {user_id}")
        
        # 檢查是否有投資組合資訊
        if not chatgpt.has_portfolio_info():
            logger.error("❌ No portfolio info available")
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text="⚠️ 請先設定投資組合資訊")
            )
            del pending_images[user_id]
            return
        
        # 分析所有圖片
        logger.info("🤖 Starting ChatGPT analysis...")
        analysis_result = chatgpt.analyze_images(images)
        logger.info(f"✅ Analysis completed, result length: {len(analysis_result)}")
        
        reply_text = f"📊 **股票圖表分析結果**\n\n{analysis_result}"
        
        # 使用 push message 回覆分析結果
        logger.info("📤 Sending push message...")
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=reply_text)
        )
        logger.info("✅ Push message sent successfully")
        
        # 清除暫存資料
        del pending_images[user_id]
        logger.info(f"🗑️ Cleaned up pending images for user {user_id}")
        
    except Exception as e:
        logger.error(f"💥 Error in process_batch_images: {str(e)}")
        logger.error(f"💥 Error type: {type(e).__name__}")
        logger.error(f"💥 Traceback: {traceback.format_exc()}")
        
        if user_id in pending_images:
            try:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text="❌ 圖片分析失敗，請稍後再試。")
                )
                logger.info("📤 Error message sent to user")
            except Exception as reply_error:
                logger.error(f"💥 Failed to send error message: {str(reply_error)}")
            
            del pending_images[user_id]

@app.route('/')
def home():
    return 'Stock Analysis Bot is running!'

@app.route("/webhook", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logger.info("Request body received")
    
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature error")
        abort(400)
    except Exception as e:
        logger.error(f"Unexpected error in callback: {str(e)}")
        abort(500)
    
    return 'OK'

@line_handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text.strip()
        user_id = event.source.user_id
        logger.info(f"💬 Received text message: {user_message}")

        # 如果有待處理的圖片，先清除
        if user_id in pending_images:
            logger.info(f"🗑️ Clearing pending images for user {user_id}")
            if pending_images[user_id]['timer']:
                pending_images[user_id]['timer'].cancel()
            del pending_images[user_id]

        # 幫助指令
        if user_message.lower() in ["help", "幫助", "說明", "?"]:
            reply_text = WELCOME_MESSAGE
            
        # 設定投資組合
        elif user_message.startswith("問股市"):
            portfolio_info = user_message[3:].strip()
            if not portfolio_info:
                reply_text = """❌ **請提供持股資訊**

正確格式：問股市 [持股狀況]

📝 **範例：**
• 問股市 持有台積電100股，成本價580元
• 問股市 想買進聯發科，預算10萬元
• 問股市 持有0050 ETF，想了解後市走勢
"""
            else:
                chatgpt.set_portfolio_info(portfolio_info)
                reply_text = f"""✅ **投資組合已設定**

📋 您的投資狀況：
{portfolio_info}

📸 **下一步：** 請傳送股票圖表截圖進行分析

💡 **多圖分析提示：**
• 可同時傳送多張圖片（系統會等待3秒收集）
• 建議上傳不同時間週期的圖表
• 系統會綜合分析並回復結果
"""
                
        # 更新投資組合
        elif user_message.startswith("更新持股"):
            portfolio_info = user_message[4:].strip()
            if not portfolio_info:
                reply_text = "請提供新的持股資訊，例如：更新持股 持有台積電300股，平均成本590元"
            else:
                chatgpt.set_portfolio_info(portfolio_info)
                reply_text = f"✅ **投資組合已更新**\n\n📋 新的投資狀況：\n{portfolio_info}"
                
        # 一般股市問題
        else:
            if not chatgpt.has_portfolio_info():
                reply_text = """⚠️ **請先設定投資組合**

請輸入「問股市 [你的持股狀況]」來設定投資組合資訊

📝 **範例：**
問股市 持有台積電200股，成本價600元，想了解是否該停利
"""
            else:
                try:
                    chatgpt.add_text_msg(user_message)
                    reply_text = chatgpt.get_response()
                except Exception as e:
                    logger.error(f"ChatGPT error: {str(e)}")
                    reply_text = "❌ 分析服務暫時無法使用，請稍後再試。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        
    except Exception as e:
        logger.error(f"💥 Error in handle_text_message: {str(e)}")
        logger.error(f"💥 Traceback: {traceback.format_exc()}")

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        user_id = event.source.user_id
        logger.info(f"📸 Received image message from user: {user_id}")
        
        # 檢查投資組合資訊
        logger.info("🔍 Checking portfolio info...")
        if not chatgpt.has_portfolio_info():
            logger.info("❌ No portfolio info found")
            reply_text = """⚠️ **請先設定投資組合**

請先輸入「問股市 [持股狀況]」設定投資組合資訊，再傳送圖表進行分析。

📝 **範例：**
問股市 持有台積電100股，成本580元
"""
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            return
        
        logger.info("✅ Portfolio info exists, proceeding with image processing...")

        try:
            # 下載圖片
            logger.info("⬇️ Downloading image content...")
            message_content = line_bot_api.get_message_content(event.message.id)
            image_data = message_content.content
            logger.info(f"✅ Image downloaded, size: {len(image_data)} bytes")
            
            # 初始化用戶的圖片暫存
            if user_id not in pending_images:
                logger.info(f"🆕 Creating new pending_images entry for user {user_id}")
                pending_images[user_id] = {
                    'images': [],
                    'user_id': user_id,
                    'timer': None
                }
            else:
                logger.info(f"📝 User {user_id} already has pending images: {len(pending_images[user_id]['images'])}")
            
            # 添加圖片到暫存
            pending_images[user_id]['images'].append(image_data)
            logger.info(f"➕ Added image to batch. Total images for user {user_id}: {len(pending_images[user_id]['images'])}")
            
            # 取消之前的計時器
            if pending_images[user_id]['timer']:
                logger.info("⏰ Cancelling previous timer")
                pending_images[user_id]['timer'].cancel()
            
            # 設定新的計時器
            logger.info(f"⏰ Setting new timer for {BATCH_WAIT_TIME} seconds")
            timer = Timer(BATCH_WAIT_TIME, process_batch_images, [user_id])
            pending_images[user_id]['timer'] = timer
            timer.start()
            logger.info("✅ Timer started successfully")
            
        except LineBotApiError as e:
            logger.error(f"💥 LINE Bot API error: {str(e)}")
            logger.error(f"💥 Error status code: {e.status_code}")
            logger.error(f"💥 Error details: {e.error.details}")
            reply_text = """❌ **圖片下載失敗**

可能原因：
• LINE API 暫時無法存取
• 圖片已過期
• 網路連線問題

💡 **建議：**
• 重新傳送圖片
• 稍後再試
"""
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            
        except Exception as e:
            logger.error(f"💥 Image processing error: {str(e)}")
            logger.error(f"💥 Error type: {type(e).__name__}")
            logger.error(f"💥 Traceback: {traceback.format_exc()}")
            
            reply_text = """❌ **圖片處理失敗**

可能原因：
• 圖片格式不支援
• 圖片太大或太小
• 系統暫時錯誤

💡 **建議：**
• 確保圖片清晰可見
• 重新截圖並傳送
• 稍後再試
"""
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
        
    except Exception as e:
        logger.error(f"💥 Error in handle_image_message: {str(e)}")
        logger.error(f"💥 Error type: {type(e).__name__}")
        logger.error(f"💥 Traceback: {traceback.format_exc()}")
        
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="❌ 系統錯誤，請稍後再試。")
            )
        except Exception as reply_error:
            logger.error(f"💥 Failed to send error reply: {str(reply_error)}")

if __name__ == "__main__":
    app.run()

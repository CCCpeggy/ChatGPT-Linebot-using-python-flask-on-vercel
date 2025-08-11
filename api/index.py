from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from api.chatgpt import ChatGPT
import os
import logging
import traceback

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(access_token)
line_handler = WebhookHandler(channel_secret)

app = Flask(__name__)

# 歡迎訊息
WELCOME_MESSAGE = """📈 **股票分析機器人**

歡迎使用專業股票分析服務！

🔸 **使用方式：**
直接傳送股票圖表截圖，系統會立即進行分析

🔸 **支援功能：**
• 技術指標分析
• 趨勢判斷
• 支撐阻力位
• 買賣建議
• 風險評估

🔸 **其他指令：**
• help - 顯示說明
• 任何股市相關問題

💡 **提示：** 上傳清晰的股票圖表可獲得更準確的分析結果
"""

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
        logger.info(f"💬 Received text message from {user_id}: {user_message}")

        # 幫助指令
        if user_message.lower() in ["help", "幫助", "說明", "?"]:
            reply_text = WELCOME_MESSAGE
            
        # 一般股市問題
        else:
            try:
                # 建立新的 ChatGPT 實例來處理文字問題
                chatgpt = ChatGPT()
                chatgpt.add_text_msg(user_message)
                reply_text = chatgpt.get_response()
                logger.info(f"✅ Text response generated for user {user_id}")
            except Exception as e:
                logger.error(f"ChatGPT error for user {user_id}: {str(e)}")
                reply_text = """❌ **分析服務暫時無法使用**

請稍後再試，或直接傳送股票圖表進行分析。

💡 **提示：** 傳送圖片可獲得更詳細的技術分析
"""

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

        try:
            # 下載圖片
            logger.info(f"⬇️ Downloading image content for user {user_id}...")
            message_content = line_bot_api.get_message_content(event.message.id)
            image_data = message_content.content
            logger.info(f"✅ Image downloaded for user {user_id}, size: {len(image_data)} bytes")
            
            # 立即分析圖片
            logger.info(f"🤖 Starting immediate analysis for user {user_id}")
            
            # 建立新的 ChatGPT 實例來分析圖片
            chatgpt = ChatGPT()
            analysis_result = chatgpt.analyze_single_image(image_data)
            
            logger.info(f"✅ Analysis completed for user {user_id}, result length: {len(analysis_result)}")
            
            reply_text = f"""📊 **股票圖表分析結果**

{analysis_result}

---
💡 **提示：** 如需更多分析，請傳送其他角度的圖表或詢問具體問題
"""
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            logger.info(f"✅ Analysis result sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"💥 Analysis error for user {user_id}: {str(e)}")
            logger.error(f"💥 Traceback: {traceback.format_exc()}")
            
            reply_text = """❌ **圖片分析失敗**

可能原因：
• 圖片格式不支援
• 圖片不夠清晰
• ChatGPT API 暫時無法使用
• 網路連線問題

💡 **建議：**
• 確保圖片清晰可見
• 重新截圖並傳送
• 稍後再試
"""
            
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_text)
                )
            except Exception as reply_error:
                logger.error(f"💥 Failed to send error reply to user {user_id}: {str(reply_error)}")
        
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

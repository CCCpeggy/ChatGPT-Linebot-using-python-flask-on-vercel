from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from api.chatgpt import ChatGPT
import os
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(access_token)
line_handler = WebhookHandler(channel_secret)

app = Flask(__name__)
chatgpt = ChatGPT()

# 歡迎訊息
WELCOME_MESSAGE = """📈 **股票分析機器人**

歡迎使用專業股票分析服務！

🔸 **使用方式：**
1️⃣ 輸入「問股市 [你的持股狀況]」
   例：問股市 持有台積電200股，成本600元

2️⃣ 傳送股票圖表截圖進行分析

3️⃣ 輸入「更新持股 [新的持股資訊]」更新投資組合

💡 **提示：** 請先設定持股資訊，再傳送圖表進行分析
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
        logger.info(f"Received text message: {user_message}")

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

📸 **下一步：** 請傳送股票圖表截圖，我將為您提供專業分析

💡 **提示：** 可隨時輸入「更新持股」修改投資組合資訊
"""
                
        # 更新投資組合
        elif user_message.startswith("更新持股"):
            portfolio_info = user_message[4:].strip()
            if not portfolio_info:
                reply_text = "請提供新的持股資訊，例如：更新持股 持有台積電300股，平均成本590元"
            else:
                chatgpt.set_portfolio_info(portfolio_info)
                reply_text = f"✅ 投資組合已更新：\n{portfolio_info}"
                
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
        logger.error(f"Error in handle_text_message: {str(e)}")

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("Received image message")
        
        if not chatgpt.has_portfolio_info():
            reply_text = """⚠️ **請先設定投資組合**

請先輸入「問股市 [持股狀況]」設定投資組合資訊，再傳送圖表進行分析。

📝 **範例：**
問股市 持有台積電100股，成本580元
"""
        else:
            try:
                # 下載圖片
                message_content = line_bot_api.get_message_content(event.message.id)
                image_data = message_content.content
                
                # 進行股票分析
                chatgpt.add_image_for_analysis(image_data)
                reply_text = chatgpt.get_response()
                
            except Exception as e:
                logger.error(f"Image analysis error: {str(e)}")
                reply_text = "❌ 圖片分析時發生錯誤，請確認圖片清晰度後重新傳送。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_image_message: {str(e)}")

if __name__ == "__main__":
    app.run()

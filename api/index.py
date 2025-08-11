from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from api.chatgpt import ChatGPT
import os
import logging
from collections import defaultdict
import time

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(access_token)
line_handler = WebhookHandler(channel_secret)

app = Flask(__name__)
chatgpt = ChatGPT()

# 用於處理多張圖片的暫存
user_images = defaultdict(list)
user_last_activity = defaultdict(float)
IMAGE_TIMEOUT = 10  # 10秒內的圖片視為同一批

# 歡迎訊息
WELCOME_MESSAGE = """📈 **股票分析機器人**

歡迎使用專業股票分析服務！

🔸 **使用方式：**
1️⃣ 輸入「問股市 [你的持股狀況]」
   例：問股市 持有台積電200股，成本600元

2️⃣ 傳送股票圖表截圖（可一次傳送多張）

💡 **多圖分析：** 可同時傳送多張圖片進行綜合分析
   • 不同時間週期（日線、週線、月線）
   • 不同技術指標圖表
   • 個股與大盤對比圖

🔸 **其他指令：**
• 更新持股 [新資訊] - 更新投資組合
• help - 顯示說明
"""

def clear_old_images():
    """清理超時的圖片暫存"""
    current_time = time.time()
    expired_users = []
    
    for user_id, last_time in user_last_activity.items():
        if current_time - last_time > IMAGE_TIMEOUT:
            expired_users.append(user_id)
    
    for user_id in expired_users:
        if user_id in user_images:
            del user_images[user_id]
        del user_last_activity[user_id]

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
        logger.info(f"Received text message: {user_message}")

        # 清理過期的圖片暫存
        clear_old_images()
        
        # 如果用戶有待處理的圖片，先清空
        if user_id in user_images:
            del user_images[user_id]
            del user_last_activity[user_id]

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
• 可同時傳送多張圖片（建議2-4張）
• 系統會在10秒內自動整合同批圖片
• 支援不同時間週期或角度的綜合分析
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
        logger.error(f"Error in handle_text_message: {str(e)}")

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        user_id = event.source.user_id
        logger.info(f"Received image message from user: {user_id}")
        
        # 清理過期的圖片暫存
        clear_old_images()
        
        if not chatgpt.has_portfolio_info():
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

        try:
            # 下載圖片
            message_content = line_bot_api.get_message_content(event.message.id)
            image_data = message_content.content
            
            # 將圖片加入用戶的暫存列表
            user_images[user_id].append(image_data)
            user_last_activity[user_id] = time.time()
            
            current_image_count = len(user_images[user_id])
            
            # 如果是第一張圖片，等待可能的後續圖片
            if current_image_count == 1:
                reply_text = f"""📸 **圖片已接收** (1張)

⏳ **等待中...** 
如果您要傳送更多圖片進行綜合分析，請在10秒內繼續傳送。

💡 **建議組合：**
• 日線 + 週線圖表
• K線 + 技術指標圖
• 個股 + 大盤對比圖

🔄 系統將在10秒後自動開始分析
"""
                
                # 設定延遲分析
                import threading
                def delayed_analysis():
                    time.sleep(IMAGE_TIMEOUT)
                    if user_id in user_images and len(user_images[user_id]) > 0:
                        try:
                            images = user_images[user_id].copy()
                            del user_images[user_id]
                            del user_last_activity[user_id]
                            
                            # 進行分析
                            if len(images) == 1:
                                chatgpt.add_single_image_for_analysis(images[0])
                            else:
                                chatgpt.add_multiple_images_for_analysis(images)
                            
                            analysis_result = chatgpt.get_response()
                            
                            # 推送分析結果
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text=f"📊 **分析完成** ({len(images)}張圖片)\n\n{analysis_result}")
                            )
                            
                        except Exception as e:
                            logger.error(f"Delayed analysis error: {str(e)}")
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text="❌ 分析過程中發生錯誤，請重新傳送圖片。")
                            )
                
                threading.Thread(target=delayed_analysis, daemon=True).start()
                
            else:
                # 多張圖片，更新狀態
                reply_text = f"""📸 **圖片已接收** ({current_image_count}張)

⏳ **繼續等待...** 
可繼續傳送更多圖片，或等待系統自動分析。

🔄 系統將在最後一張圖片後10秒開始分析
"""
            
        except Exception as e:
            logger.error(f"Image processing error: {str(e)}")
            reply_text = "❌ 圖片處理時發生錯誤，請確認圖片清晰度後重新傳送。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_image_message: {str(e)}")

if __name__ == "__main__":
    app.run()

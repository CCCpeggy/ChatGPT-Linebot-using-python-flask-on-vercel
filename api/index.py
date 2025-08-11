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
chatgpt = ChatGPT()

# 用於暫存用戶圖片的字典
user_images = {}

# 歡迎訊息
WELCOME_MESSAGE = """📈 **股票分析機器人**

歡迎使用專業股票分析服務！

🔸 **使用方式：**
1️⃣ 輸入「問股市 [你的持股狀況]」
   例：問股市 持有台積電200股，成本600元

2️⃣ 傳送股票圖表截圖
   • 可以傳送多張圖片
   • 系統會暫存您的圖片

3️⃣ 輸入「分析」或「幫我分析」
   • 系統會分析所有已傳送的圖片
   • 提供綜合分析結果

🔸 **其他指令：**
• 更新持股 [新資訊] - 更新投資組合
• 清除圖片 - 清除暫存的圖片
• help - 顯示說明
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
        logger.info(f"💬 Received text message: {user_message}")

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

📸 **下一步：** 
1. 傳送股票圖表截圖（可傳送多張）
2. 輸入「分析」開始分析

💡 **使用提示：**
• 可以先傳送多張圖片再一起分析
• 支援各種股票圖表和技術指標
"""
                
        # 更新投資組合
        elif user_message.startswith("更新持股"):
            portfolio_info = user_message[4:].strip()
            if not portfolio_info:
                reply_text = "請提供新的持股資訊，例如：更新持股 持有台積電300股，平均成本590元"
            else:
                chatgpt.set_portfolio_info(portfolio_info)
                reply_text = f"✅ **投資組合已更新**\n\n📋 新的投資狀況：\n{portfolio_info}"
        
        # 分析指令
        elif user_message in ["分析", "幫我分析", "開始分析", "analyze"]:
            if not chatgpt.has_portfolio_info():
                reply_text = """⚠️ **請先設定投資組合**

請輸入「問股市 [你的持股狀況]」來設定投資組合資訊

📝 **範例：**
問股市 持有台積電200股，成本價600元
"""
            elif user_id not in user_images or not user_images[user_id]:
                reply_text = """📸 **請先傳送圖片**

請先傳送股票圖表截圖，然後再輸入「分析」

💡 **提示：**
• 可以傳送多張圖片
• 支援各種股票圖表格式
• 建議上傳清晰的圖表
"""
            else:
                try:
                    images = user_images[user_id]
                    logger.info(f"🤖 Starting analysis for {len(images)} images")
                    
                    # 分析所有圖片
                    analysis_result = chatgpt.analyze_images(images)
                    logger.info(f"✅ Analysis completed, result length: {len(analysis_result)}")
                    
                    reply_text = f"""📊 **股票圖表分析結果**
（已分析 {len(images)} 張圖片）

{analysis_result}

---
💡 **提示：** 圖片已分析完成，如需重新分析請重新傳送圖片
"""
                    
                    # 清除已分析的圖片
                    del user_images[user_id]
                    logger.info(f"🗑️ Cleared images for user {user_id}")
                    
                except Exception as e:
                    logger.error(f"💥 Analysis error: {str(e)}")
                    logger.error(f"💥 Traceback: {traceback.format_exc()}")
                    reply_text = """❌ **圖片分析失敗**

可能原因：
• ChatGPT API 暫時無法使用
• 圖片格式問題
• 網路連線問題

💡 **建議：**
• 重新傳送圖片
• 稍後再試
• 確保圖片清晰可見
"""
        
        # 清除圖片指令
        elif user_message in ["清除圖片", "清除", "clear", "重置"]:
            if user_id in user_images:
                image_count = len(user_images[user_id])
                del user_images[user_id]
                reply_text = f"🗑️ **已清除 {image_count} 張暫存圖片**\n\n請重新傳送要分析的圖片"
            else:
                reply_text = "📭 **目前沒有暫存的圖片**\n\n請傳送圖片後再進行分析"
                
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
            if user_id not in user_images:
                user_images[user_id] = []
                logger.info(f"🆕 Created new image storage for user {user_id}")
            
            # 添加圖片到暫存
            user_images[user_id].append(image_data)
            image_count = len(user_images[user_id])
            logger.info(f"➕ Added image to storage. Total images for user {user_id}: {image_count}")
            
            # 回覆確認訊息
            reply_text = f"""📸 **圖片已收到** ({image_count}/10)

✅ 已暫存您的圖片

📝 **下一步：**
• 繼續傳送更多圖片，或
• 輸入「分析」開始分析

💡 **其他指令：**
• 清除圖片 - 清除暫存的圖片
• help - 查看使用說明
"""
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            logger.info("✅ Confirmation message sent")
            
        except LineBotApiError as e:
            logger.error(f"💥 LINE Bot API error: {str(e)}")
            logger.error(f"💥 Error status code: {e.status_code}")
            if hasattr(e, 'error') and hasattr(e.error, 'details'):
                logger.error(f"💥 Error details: {e.error.details}")
            
            reply_text = """❌ **圖片處理失敗**

可能原因：
• LINE API 暫時無法存取
• 圖片已過期
• 網路連線問題

💡 **建議：**
• 重新傳送圖片
• 稍後再試
"""
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_text)
                )
            except Exception as reply_error:
                logger.error(f"💥 Failed to send error reply: {str(reply_error)}")
            
        except Exception as e:
            logger.error(f"💥 Image processing error: {str(e)}")
            logger.error(f"💥 Error type: {type(e).__name__}")
            logger.error(f"💥 Traceback: {traceback.format_exc()}")
            
            reply_text = """❌ **圖片暫存失敗**

可能原因：
• 圖片格式不支援
• 圖片太大
• 系統暫時錯誤

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
                logger.error(f"💥 Failed to send error reply: {str(reply_error)}")
        
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

import os
import base64

MSG_LIST_LIMIT = int(os.getenv("MSG_LIST_LIMIT", default=10))

# 股票分析師的專業指導原則
STOCK_ANALYST_GUIDELINES = """
你是一位專業的股票分析師，專門提供台股、美股、港股、原物料等市場的技術分析和投資建議。

【專業背景】
- 擁有豐富的技術分析和基本面分析經驗
- 熟悉各種技術指標、圖表型態和市場趨勢
- 了解不同市場的交易特性和風險因子

【分析原則】
- 基於客觀數據和圖表進行分析
- 同時考慮技術面、基本面、籌碼面和消息面
- 提供風險評估和操作建議
- 強調投資風險，不提供明確買賣點位

【多圖分析要求】
當收到多張圖片時，請：
1. 先分別分析每張圖片的重點
2. 再進行綜合比較和判斷
3. 提供整體性的投資建議

【回覆格式要求】
請嚴格按照以下格式回覆：

📊 **技術分析**
- 技術指標解讀（如：RSI、MACD、KD等）
- 圖表型態判讀（如：頭肩頂、雙底、三角整理等）
- 支撐阻力位分析
- 成交量分析
- （如有多張圖）不同時間週期或角度的比較分析

💰 **投資建議**
- 針對用戶持股狀況的具體建議
- 風險評估與資金配置建議
- 進出場時機參考
- 停損停利設定建議

⚠️ **風險提醒**
- 主要風險因子識別
- 市場環境變化提醒
- 個股特殊風險注意事項

📈 *各時間週期重點關注**
- 30分鐘線：當日高低點、量價配合、短期突破
- 日線：近期趨勢、支撐阻力、技術指標轉折
- 週線：中期趨勢確認、重要技術位測試
- 月線：長期趨勢方向、基本面配合度

"""

class Prompt:
    def __init__(self):
        self.msg_list = []
        self.portfolio_info = ""
        self._initialize_system_prompt()
    
    def _initialize_system_prompt(self):
        """初始化系統提示"""
        self.msg_list = [{
            "role": "system", 
            "content": STOCK_ANALYST_GUIDELINES
        }]
    
    def set_portfolio_info(self, portfolio_info):
        """設定投資組合資訊"""
        self.portfolio_info = portfolio_info
        # 如果已有投資組合資訊，更新它
        portfolio_msg_exists = False
        for i, msg in enumerate(self.msg_list):
            if (msg["role"] == "user" and 
                isinstance(msg["content"], str) and 
                "投資狀況：" in msg["content"]):
                self.msg_list[i]["content"] = f"我的投資狀況：{portfolio_info}"
                portfolio_msg_exists = True
                break
        
        # 如果沒有投資組合資訊，添加它
        if not portfolio_msg_exists:
            self.msg_list.append({
                "role": "user", 
                "content": f"我的投資狀況：{portfolio_info}"
            })
    
    def add_msg(self, new_msg):
        """添加一般文字訊息"""
        if len(self.msg_list) >= MSG_LIST_LIMIT:
            self._trim_messages()
        
        self.msg_list.append({"role": "user", "content": new_msg})
    
    def add_image_msg(self, image_data_list, portfolio_info):
        """添加包含圖片的訊息進行股票分析"""
        if len(self.msg_list) >= MSG_LIST_LIMIT:
            self._trim_messages()
        
        # 根據圖片數量決定提示文字
        if len(image_data_list) == 1:
            analysis_text = f"請根據我的投資狀況分析以下股票圖表：\n投資狀況：{portfolio_info}\n\n請提供詳細的技術分析和投資建議。"
        else:
            analysis_text = f"請根據我的投資狀況綜合分析以下{len(image_data_list)}張股票圖表：\n投資狀況：{portfolio_info}\n\n請分別分析每張圖表，然後提供綜合性的投資建議。"
        
        message_content = [
            {
                "type": "text",
                "text": analysis_text
            }
        ]
        
        # 添加所有圖片
        for i, image_data in enumerate(image_data_list):
            if isinstance(image_data, bytes):
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            else:
                image_base64 = image_data
            
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            })
        
        self.msg_list.append({
            "role": "user", 
            "content": message_content
        })
    
    def _trim_messages(self):
        """修剪訊息列表，保留系統訊息和投資組合資訊"""
        system_msgs = [msg for msg in self.msg_list if msg["role"] == "system"]
        portfolio_msg = None
        
        # 找到投資組合資訊
        for msg in self.msg_list:
            if (msg["role"] == "user" and 
                isinstance(msg["content"], str) and 
                "投資狀況：" in msg["content"]):
                portfolio_msg = msg
                break
        
        self.msg_list = system_msgs
        if portfolio_msg:
            self.msg_list.append(portfolio_msg)
    
    def generate_prompt(self):
        return self.msg_list

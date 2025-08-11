from api.prompt import Prompt
import os
from openai import OpenAI
import base64

client = OpenAI()
client.api_key = os.getenv("OPENAI_API_KEY")

class ChatGPT:
    def __init__(self):
        self.prompt = Prompt()
        self.model = os.getenv("OPENAI_MODEL", default="gpt-4o")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", default=0.3))
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", default=2000))
        self.user_portfolio_info = ""

    def get_response(self):
        response = client.chat.completions.create(
            model=self.model,
            messages=self.prompt.generate_prompt(),
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        return response.choices[0].message.content

    def set_portfolio_info(self, portfolio_info):
        """設定投資組合資訊"""
        self.user_portfolio_info = portfolio_info
        self.prompt.set_portfolio_info(portfolio_info)

    def add_text_msg(self, text):
        """添加文字訊息"""
        self.prompt.add_msg(text)

    def analyze_images(self, image_data_list):
        """分析圖片並立即返回結果"""
        self.prompt.add_image_msg(image_data_list, self.user_portfolio_info)
        return self.get_response()

    def has_portfolio_info(self):
        """檢查是否已設定投資組合資訊"""
        return bool(self.prompt.portfolio_info.strip())


    def analyze_single_image(self, image_data):
        """分析單張圖片並立即返回結果"""
        temp_prompt = Prompt()
        
        # 設定一個通用的投資組合資訊（因為沒有用戶狀態）
        default_portfolio = "一般投資者，希望獲得以是否要進場做多/做空與是否要出場做多/做空分析"
        
        # 使用 Prompt 類別的 add_image_msg 方法
        temp_prompt.add_image_msg([image_data], default_portfolio)
        
        # 直接調用 OpenAI API
        response = client.chat.completions.create(
            model=self.model,
            messages=temp_prompt.generate_prompt(),
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        
        return response.choices[0].message.content
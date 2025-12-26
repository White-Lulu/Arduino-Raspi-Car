#!/usr/bin/env python
# coding: utf-8
import azure.cognitiveservices.speech as speechsdk
import openai
import asyncio
import requests
import os
import time
import subprocess

# ================= 配置区域 =================
# 1. Flask 小车服务器地址 (本地)
CAR_SERVER_URL = "http://127.0.0.1:5000/move"

# 2. Azure 语音服务配置
AZURE_SPEECH_KEY = ""
AZURE_REGION = "eastasia" # 例如 eastasia, westus 等
VOICE_NAME = "zh-CN-XiaoxiaoNeural" # 声音选择

# 3. OpenAI / DeepSeek 配置
OPENAI_API_KEY = "sk-6e33416ab8ef4e919c4340310ad74477"
OPENAI_API_BASE = "https://api.deepseek.com/v1" 
MODEL_NAME = "deepseek-chat" # 或 deepseek-chat

# ===========================================

# 初始化 OpenAI 客户端
client = openai.AsyncClient(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)

# 定义系统提示词
SYSTEM_PROMPT = {
    "role": "system", 
    "content": """
    你是一个搭载在麦克纳姆轮小车上的智能助手。你可以和用户闲聊。
    但如果用户明确下达了移动指令，请在回复的文本末尾加上控制暗号。

    1. **视觉跟踪**：如果用户说“跟踪xx”、“跟着xx走”，请推断该物体在 COCO 数据集中的 ID，并在回复末尾加上：
       ||TRACK:<ID>
       
       常见 ID 参考：
       人-0, 自行车-1, 汽车-2, 猫-15, 狗-16, 
       背包-24, 球-32, 瓶子-39, 杯子-41, 椅子-56, 手机-67。
       
       例如：
       用户："跟着这个瓶子走。"
       你："好的，正在锁定瓶子。||TRACK:39"
       
       用户："别跟了。"
       你："已停止跟踪。||TRACK:STOP"
    
    2. **运动控制** (用双竖线分隔，末尾不要加句号)：
       - 前进 -> ||F
       - 后退 -> ||B
       - 左转/旋转 -> ||L
       - 右转/旋转 -> ||R
       - 停止/刹车 -> ||S
       - 左横移/向左平移 -> ||Q   <-- 新增逻辑
       - 右横移/向右平移 -> ||E   <-- 新增逻辑
    
    例如：
    用户："前面有障碍物，倒退一点。"
    你："好的，正在后退。||B"

    用户："往左边横着挪一点。"
    你："好的，正在向左平移。||Q"
    
    用户："右边有个缝隙，横着过去。"
    你："没问题，向右横移。||E"
    """
}   

conversation_history = [SYSTEM_PROMPT]
vision_process = None # 全局变量记录视觉进程

def remote_log(text, prefix="[AI]"):
    """把日志发送到 Flask 网页终端"""
    try:
        # URL 编码并发送
        requests.get(f"http://127.0.0.1:5000/api/log_message", params={"msg": f"{prefix} {text}"}, timeout=0.1)
    except:
        pass # 发送失败不影响主程序

def manage_vision(action, class_id=0):
    """启动或关闭视觉脚本 (修复版)"""
    global vision_process
    
    # 1. 先彻底清理旧进程
    if vision_process:
        print(">> 正在停止旧的视觉任务...", end="", flush=True)
        vision_process.terminate() # 发送 SIGTERM 信号
        
        # 等待进程真正结束，防止僵尸进程
        try:
            vision_process.wait(timeout=3) 
        except subprocess.TimeoutExpired:
            vision_process.kill() # 如果卡住，强制杀掉
            
        vision_process = None
        print(" [已停止]")
        
        # 等待 3 秒，让摄像头和端口释放
        print(">> 等待资源释放 (3s)...")
        time.sleep(3.0) 
        
    # 2. 启动新任务
    if action == "START":
        print(f">> 启动新视觉跟踪，目标 ID: {class_id}")
        try:
            vision_process = subprocess.Popen(
                ["libcamerify", "python3", "vision_tracker.py", str(class_id)],
                stdout=None, # 让输出直接打印到控制台
                stderr=None
            )
            
            # 稍微等一下，让 Flask 有时间启动
            time.sleep(2.0) 
            print(">> 视觉进程已加载")
            
        except Exception as e:
            print(f"!!! 启动视觉脚本失败: {e}")

def control_car(cmd_code):
    """发送指令给 Flask 服务器"""
    try:
        print(f">> 发送控制指令: {cmd_code}")
        requests.get(f"{CAR_SERVER_URL}?cmd={cmd_code}", timeout=0.5)
    except Exception as e:
        print(f"小车连接失败: {e}")

async def ask_ai_and_speak(text, synthesizer):
    """发送文本给 AI，获取回复，分离指令，并朗读"""
    global conversation_history
    conversation_history.append({"role": "user", "content": text})
    
    # 保持上下文长度适中
    if len(conversation_history) > 10:
        conversation_history = [SYSTEM_PROMPT] + conversation_history[-8:]

    print("AI 思考中...")
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation_history
        )
        
        full_reply = response.choices[0].message.content
        conversation_history.append({"role": "assistant", "content": full_reply})
        
        # === 记录用户和 AI 的对话到网页终端 ===
        remote_log(text, prefix="[USER]") 
        remote_log(full_reply, prefix="[AI]") 
        
        # === 解析指令 ===
        speak_text = full_reply
        command = None
        track_id = None
        
        if "||" in full_reply:
            parts = full_reply.split("||")
            speak_text = parts[0]
            cmd_part = parts[1].strip()
            
            # 判断是跟踪指令还是运动指令
            if cmd_part.startswith("TRACK:"):
                track_val = cmd_part.split(":")[1]
                if track_val == "STOP":
                    manage_vision("STOP")
                else:
                    try:
                        track_id = int(track_val)
                        manage_vision("START", track_id)
                    except:
                        print(f"ID 解析错误: {track_val}")
            else:
                command = cmd_part.upper() # F, B, L, R, S
        
        print(f"AI 回复: {speak_text}")
        
        # === 并行执行 ===
        # 现在这里的 synthesizer 变量能正确找到了
        speech_future = synthesizer.speak_text_async(speak_text)
        
        # 如果有普通运动指令
        if command:
            control_car(command)
            if command in ['F', 'B', 'L', 'R']:
                time.sleep(1.0) 
                control_car('S') 
                
        speech_future.get()

    except Exception as e:
        print(f"AI 交互出错: {e}")
        synthesizer.speak_text_async("我的大脑有点短路了。")

async def main():
    # 配置 Azure 语音
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = "zh-CN"
    speech_config.speech_synthesis_voice_name = VOICE_NAME
    
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    audio_out_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_out_config)

    print("=== 语音小车助手已启动 ===")

    while True:
        print("\n正在聆听... (请对着麦克风说话)")
        try:
            result = recognizer.recognize_once_async().get()
            
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = result.text
                print(f"你说了: {text}")

                if len(text) < 2: continue
                if "退出" in text: break
                
                await ask_ai_and_speak(text, synthesizer)
                
            elif result.reason == speechsdk.ResultReason.NoMatch:
                print("没有检测到语音")
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                print(f"!!! 语音识别被取消: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    print(f"!!! 错误详情: {cancellation_details.error_details}")

        except Exception as e:
            print(f"主循环错误: {e}")
            time.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        manage_vision("STOP")
        print("程序停止")
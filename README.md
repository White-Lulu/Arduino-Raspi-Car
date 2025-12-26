
# Raspberry Pi AI Mecanum Robot (树莓派 AI 麦克纳姆轮机器人)

An omnidirectional mobile robot project integrating Computer Vision (YOLOv8), Large Language Models (DeepSeek/OpenAI), Voice Interaction (Azure Speech), and Web-based control.

## 📖 项目概述

该系统采用 Host-Slave 架构：

- **Host (Raspberry Pi 4B)**: 负责高层计算，包括 Flask Web 服务、YOLOv8 目标检测、LLM 决策以及语音处理。
- **Slave (Arduino Uno R3)**: 负责实时电机 PWM 控制与舵机动作。

主要特性：

- **全向运动**：麦克纳姆轮支持前进/后退、转向与横移（侧向平移）。
- **AI 大脑**：使用 Azure Speech（STT/TTS）和 DeepSeek/OpenAI（LLM）。AI 能将自然语言解析为运动命令（如“向左移动”）或视觉任务（如“跟踪瓶子”）。
- **视觉跟踪**：基于 YOLOv8n 的实时目标跟踪，机器人自动转向并移动以保持目标居中。
- **智能避障**：`car_server.py` 中的逻辑：当物体距离 < 30cm 时触发紧急停止，并通过舵机扫描寻找可行路径。
- **Web 仪表盘**：基于 Flask 的网页界面用于手动控制、视频流与实时日志查看。

---

## 🛠 硬件架构

### 物料清单 (BOM)

| 组件 | 说明 |
|------|------|
| 主板 | Raspberry Pi 4B（建议 4GB+） |
| 运动控制 | Arduino Uno R3 |
| 电机驱动 | L293D Motor Shield v1 |
| 电机 | 4 × TT DC 减速电机（1:48） |
| 车轮 | 4 × 麦克纳姆轮（全向） |
| 摄像头 | OV5647 5MP CSI Camera |
| 显示 | 0.96" OLED（I2C，SH1106） |
| 传感器 | HC-SR04 超声波测距 |
| 逻辑电源 | 5V 3A 移动电源（Type-C 给 RPi） |
| 驱动电源 | 2 × 18650 锂电池（7.4V，接到 L293D EXT_PWR） |

### 引脚配置

1. Arduino <-> L293D & Motors

| 组件 | Arduino 引脚 / Motor Shield 端口 | 说明 |
|------|-------------------------------|------|
| 左前 (LF) | M1 | AF_DCMotor(1) |
| 左后 (LR) | M2 | AF_DCMotor(2) |
| 右前 (RF) | M3 | AF_DCMotor(3) |
| 右后 (RR) | M4 | AF_DCMotor(4) |
| 舵机 | Servo_2 (Pin 9) | 超声波扫描用 |

2. Raspberry Pi GPIO (BCM)

| 组件 | RPi GPIO (BCM) | 物理引脚 | 功能 |
|------|----------------|---------|------|
| 超声波 Trig | GPIO 23 | Pin 16 | 紧急刹车触发 |
| 超声波 Echo | GPIO 24 | Pin 18 | 距离测量 |
| OLED SDA | GPIO 2 | Pin 3 | I2C 数据 |
| OLED SCL | GPIO 3 | Pin 5 | I2C 时钟 |
| 连接 | USB 端口 | - | 串口通信（/dev/ttyACM0） |

---

## 📂 软件架构

目录结构：

```
.
├── car_server.py        # [CORE] Flask server (Port 5000), Serial bridge, Avoidance logic
├── vision_tracker.py    # [EYES] YOLOv8 detection thread & Video Stream (Port 5001)
├── voice_controller.py  # [BRAIN] Azure Speech + LLM + Command parsing
├── oled.server.py       # [UI] System stats monitor (IP/CPU/RAM)
├── robot_firmware.ino   # [MCU] Arduino C++ firmware
└── yolov8n.pt           # Pre-trained YOLO weights
```

模块说明：

1. car_server.py（中央控制）

- Web 控制面板：运行在 http://<RPi_IP>:5000，提供全向运动按钮（前进、后退、旋转、左右平移）。
- 串口桥接：以 9600 波特率与 Arduino 通信。
- 安全逻辑：后台线程监控 HC-SR04，当距离 < 30cm 时：触发紧急停止；若接收到“前进”指令则执行自动扫描（舵机左右）并计算更安全路径后转向。

2. vision_tracker.py（视觉）

- 推断：运行 YOLOv8n（可选 int8 优化或标准模型）。
- 跟踪 PID：计算目标边界框中心，向 `car_server` 发送 L/R/F/S 命令以保持目标居中并达到目标距离（通过目标高度比率判断）。
- 视频流：MJPEG 流地址 http://<RPi_IP>:5001/video_feed。

3. voice_controller.py（交互）

- 系统提示：定义 AI 角色与控制协议。
- 流程：
	1. 使用麦克风监听（Azure STT）。
	2. 将识别文本发送到 DeepSeek/OpenAI。
	3. LLM 返回文本并可附带隐藏控制命令（例如 `||TRACK:39` 表示跟踪瓶子、`||Q` 表示左滑）。
	4. Python 执行命令并使用 Azure TTS 播报反馈。

---

## ⚙️ 安装与配置

### 1. Arduino 设置

1. 安装 Arduino IDE。
2. 安装库：Adafruit Motor Shield (V1) 与 Servo。
3. 将 `robot_firmware.ino` 刷写到 Arduino Uno。

### 2. Raspberry Pi 设置

系统：Raspberry Pi OS（Bullseye / Bookworm）、Python 3.9+

1. 启用接口：

```bash
sudo raspi-config
# Enable: Camera, I2C, Serial Port (Disable console shell, Enable hardware)
```

2. 安装系统依赖：

```bash
sudo apt-get update
sudo apt-get install libopenblas-dev libhdf5-dev libatlas-base-dev libjasper-dev libqtgui4 libqt4-test
```

3. 安装 Python 库：

```bash
pip3 install flask pyserial gpiozero luma.oled opencv-python ultralytics azure-cognitiveservices-speech openai
```

4. 配置 `voice_controller.py`：在脚本中填写 API key

```python
AZURE_SPEECH_KEY = "Your_Azure_Key"
AZURE_REGION     = "eastasia"  # 或你的区域
OPENAI_API_KEY   = "Your_DeepSeek_or_OpenAI_Key"
OPENAI_API_BASE  = "https://api.deepseek.com/v1"
```

---

## 🚀 使用指南

建议使用 `screen` 或多个终端窗口分别运行各个服务。

步骤 1：启动中央控制器（必须先启动以建立串口与 Web API）

```bash
python3 car_server.py
```

- 打开控制面板：访问 http://<RPi_IP>:5000

步骤 2：启动系统监控（可选）

```bash
python3 oled.server.py &
```

步骤 3：启动语音与 AI 助手（会在需要时管理 vision_tracker.py）

```bash
python3 voice_controller.py
```

语音示例命令（AI 会返回控制码）：

- 运动类：
	- 用户：“向前移动一点。” -> AI：`||F`
	- 用户：“向左滑动。” -> AI：`||Q`（左侧平移）
	- 用户：“向右滑动。” -> AI：`||E`（右侧平移）
- 跟踪（COCO ID 示例）：
	- 用户：“跟踪这个瓶子。” -> AI：`||TRACK:39`（启动 `vision_tracker.py` 并跟踪 ID=39）
	- 用户：“停止跟踪。” -> AI：`||TRACK:STOP`（终止视觉进程）

---

## 🐛 故障排查

- 串口错误：若 `car_server.py` 无法连接，检查 Arduino 是否插好并确认代码中的端口（如 `/dev/ttyACM0` 或 `/dev/ttyUSB0`）。
- 摄像头延迟：若 5001 端口的视频流卡顿，确保 `vision_tracker.py` 使用 `yolov8n.pt`（nano 模型），不要使用更大的模型。
- 无音频：检查 `alsamixer`，确保 USB 麦克风为默认输入设备。

---

## 附：快速链接与文件

- 中央控制：`car_server.py`
- 视觉：`vision_tracker.py`
- 语音/AI：`voice_controller.py`
- OLED 显示：`oled.server.py`
- Arduino 固件：`robot_firmware.ino`
- YOLO 权重：`yolov8n.pt`



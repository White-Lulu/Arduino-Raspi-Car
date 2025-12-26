import serial
import threading
from flask import Flask, render_template_string, request
from gpiozero import DistanceSensor
import time
from collections import deque
import json

# ===================================================================
# 配置区域
# ===================================================================
SERIAL_PORT = '/dev/ttyACM0'  # 确认端口
BAUD_RATE = 9600
MIN_EMERGENCY_DISTANCE = 30.0 # 触发避障的距离 (cm)

# ===================================================================
# 1. 串口与状态管理
# ===================================================================
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
    print(f"成功连接到 Arduino 端口 {SERIAL_PORT}")
except Exception as e:
    print(f"!!! 错误: 无法连接到 {SERIAL_PORT}。 {e}")
    ser = None

# 全局状态锁
obstacle_state = {
    "lock": threading.Lock(),
    "emergency_stop": False,
}

def send_to_arduino(command):
    if ser:
        try:
            ser.write(command.encode('utf-8'))
            # print(f"发送 -> Arduino: {command}") # 调试时可打开
        except Exception as e:
            print(f"!!! 串口写入错误: {e}")

# ===================================================================
# 2. 传感器逻辑 (GPIOZERO)
# ===================================================================
def emergency_brake_detected():
    """距离过近，立刻停车"""
    global obstacle_state
    with obstacle_state["lock"]:
        if obstacle_state["emergency_stop"]:
            return
        add_log(f"!!! 触发紧急刹车 (<{MIN_EMERGENCY_DISTANCE}cm) !!!")
        obstacle_state["emergency_stop"] = True
    
    send_to_arduino('S') # 物理停车

def emergency_brake_cleared():
    """距离恢复安全"""
    global obstacle_state
    with obstacle_state["lock"]:
        if obstacle_state["emergency_stop"]:
            add_log("--- 障碍解除 ---")
            obstacle_state["emergency_stop"] = False

try:
    # 超声波引脚 (BCM编码)
    GPIO_TRIG = 23
    GPIO_ECHO = 24
    
    ultrasonic_sensor = DistanceSensor(echo=GPIO_ECHO, trigger=GPIO_TRIG)
    ultrasonic_sensor.threshold_distance = MIN_EMERGENCY_DISTANCE / 100.0
    ultrasonic_sensor.when_in_range = emergency_brake_detected
    ultrasonic_sensor.when_out_of_range = emergency_brake_cleared
    
    print(f"超声波传感器就绪 (T:{GPIO_TRIG}, E:{GPIO_ECHO})")

except Exception as e:
    print(f"!!! 传感器初始化失败: {e}")
    ultrasonic_sensor = None

# ===================================================================
# 3. 网页服务器
# ===================================================================

LOG_BUFFER = deque(maxlen=20) # 只保留最近 20 条记录的日志队列

def add_log(message):
    """添加日志并打印到后台控制台"""
    print(message) # 保持后台可见
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    LOG_BUFFER.append(f"[{timestamp}] {message}")
    
app = Flask(__name__)

HTML_CONTROLLER = """
<!DOCTYPE html>
<html>
<head>
    <title>RPi 麦克纳姆全向控</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
    <style>
        body {
            font-family: 'Courier New', monospace; /* 终端字体 */
            text-align: center;
            background-color: #1e1e1e; /* 深灰背景 */
            color: #ecf0f1;
            margin: 0;
            padding-bottom: 20px;
            display: flex;
            flex-direction: column;
            justify-content: center; /* 垂直居中 */
            align-items: center;
            height: 100vh;
        }
        /* 视频容器 */
        .video-container {
            margin-top: 10px;
            width: 300px;
            height: 225px;
            background-color: #000;
            border: 2px solid #555;
            border-radius: 4px;
            overflow: hidden;
            flex-shrink: 0;
        }
        img { width: 100%; height: 100%; object-fit: cover; }
        
        /* === 控制面板 === */
        .control-panel {
            margin: 15px 0;
            display: grid;
            grid-template-rows: 60px 100px 60px;
            grid-template-columns: 70px 120px 70px;
            gap: 8px;
            align-items: center;
            justify-items: center;
            flex-shrink: 0;
        }

        /* 按钮通用样式 */
        .btn {
            background-color: #3a3a3a;
            color: #00d2ff; /* 科技蓝图标 */
            border: 1px solid #555;
            border-radius: 10px;
            box-shadow: 0 4px #222;
            font-size: 28px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.1s;
        }
        .btn:active {
            background-color: #00d2ff;
            color: #000;
            transform: translateY(2px);
            box-shadow: 0 2px #222;
        }

        /* 布局定位 */
        #btn-fwd  { width: 100%; height: 100%; grid-row: 1; grid-column: 2; border-radius: 15px 15px 5px 5px; }
        #btn-back { width: 100%; height: 100%; grid-row: 3; grid-column: 2; border-radius: 5px 5px 15px 15px; }
        
        #btn-slide-left  { width: 100%; height: 80%; grid-row: 2; grid-column: 1; }
        #btn-slide-right { width: 100%; height: 80%; grid-row: 2; grid-column: 3; }

        /* 中间圆环 */
        .rotate-cluster {
            grid-row: 2; grid-column: 2;
            position: relative;
            width: 100px; height: 100px;
            background-color: #252525;
            border-radius: 50%;
            border: 2px solid #444;
        }
        #btn-rot-left {
            position: absolute; top: -1px; left: -1px;
            width: 50px; height: 100px;
            background: transparent; border: none; box-shadow: none;
            border-radius: 50px 0 0 50px;
            color: #ff9f43; /* 橙色旋转 */
        }
        #btn-rot-right {
            position: absolute; top: -1px; right: -1px;
            width: 50px; height: 100px;
            background: transparent; border: none; box-shadow: none;
            border-radius: 0 50px 50px 0;
            color: #ff9f43;
        }
        /* 停止按钮 (红点) */
        #btn-stop {
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 40px; height: 40px;
            background-color: #e74c3c;
            border-radius: 50%;
            border: 2px solid #c0392b;
            color: white; font-size: 14px;
        }
        #btn-stop:active { background-color: #c0392b; }

        /* === 终端窗口 === */
        .terminal-window {
            width: 90%;
            max-width: 400px;
            height: 150px;
            background-color: #000;
            border: 1px solid #00ff00;
            border-radius: 4px;
            padding: 10px;
            box-sizing: border-box;
            overflow-y: auto;
            text-align: left;
            font-size: 12px;
            line-height: 1.4;
            color: #00ff00; /* 黑客绿 */
            text-shadow: 0 0 2px #00ff00;
            margin-bottom: 10px;
        }
        .log-line { margin: 2px 0; border-bottom: 1px dashed #333; }
        .log-sys { color: #00d2ff; }
        .log-ai  { color: #ff9f43; }
        .log-warn{ color: #ff4757; }

    </style>
</head>
<body>
    <div class="video-container">
        <img id="cam-stream" src="" alt="NO SIGNAL">
    </div>

    <div class="control-panel">
        <button id="btn-fwd" class="btn">▲</button>
        <button id="btn-slide-left" class="btn">◀</button>
        <div class="rotate-cluster">
            <button id="btn-rot-left" class="btn"></button>
            <button id="btn-rot-right" class="btn"></button>
            <button id="btn-stop" class="btn">■</button>
        </div>
        <button id="btn-slide-right" class="btn">▶</button>
        <button id="btn-back" class="btn">▼</button>
    </div>

    <div class="terminal-window" id="terminal">
        <div class="log-line">System initialized...</div>
        <div class="log-line">Waiting for logs...</div>
    </div>

    <script>
        const host = window.location.hostname;
        const streamUrl = `http://${host}:5001/video_feed`;
        document.getElementById('cam-stream').src = streamUrl;

        // 按钮映射
        const bindings = [
            { id: 'btn-fwd', cmd: 'F' },
            { id: 'btn-back', cmd: 'B' },
            { id: 'btn-slide-left', cmd: 'Q' }, 
            { id: 'btn-slide-right', cmd: 'E' },
            { id: 'btn-rot-left', cmd: 'L' },
            { id: 'btn-rot-right', cmd: 'R' },
            { id: 'btn-stop', cmd: 'S' }
        ];

        bindings.forEach(item => {
            const btn = document.getElementById(item.id);
            btn.addEventListener('touchstart', (e) => { e.preventDefault(); sendCommand(item.cmd); });
            btn.addEventListener('touchend', (e) => { e.preventDefault(); sendCommand('S'); });
            btn.addEventListener('mousedown', () => sendCommand(item.cmd));
            btn.addEventListener('mouseup', () => sendCommand('S'));
        });
        document.getElementById('btn-stop').addEventListener('click', () => sendCommand('S'));

        function sendCommand(cmd) {
            fetch(`/move?cmd=${cmd}`);
        }

        // === 终端日志轮询 ===
        const term = document.getElementById('terminal');
        
        setInterval(() => {
            fetch('/api/get_logs')
                .then(res => res.json())
                .then(data => {
                    // 清空并重新渲染
                    term.innerHTML = ""; 
                    data.forEach(line => {
                        const div = document.createElement('div');
                        div.className = 'log-line';
                        // 简单的颜色高亮处理
                        if(line.includes("[AI]")) div.className += " log-ai";
                        if(line.includes("!!!")) div.className += " log-warn";
                        if(line.includes("CMD")) div.className += " log-sys";
                        div.innerText = line;
                        term.appendChild(div);
                    });
                    // 自动滚动到底部
                    term.scrollTop = term.scrollHeight;
                });
        }, 1000); // 每秒刷新一次
    </script>
</body>
</html>
"""

# ===================================================================
# 5. Flask 路由 (全新逻辑)
# ===================================================================

@app.route('/')
def index():
    return render_template_string(HTML_CONTROLLER)

# 接收外部日志的接口
@app.route('/api/log_message')
def api_log_message():
    msg = request.args.get('msg')
    if msg:
        add_log(msg)
    return "OK"

# 给前端提供日志数据
@app.route('/api/get_logs')
def api_get_logs():
    return json.dumps(list(LOG_BUFFER))

@app.route('/move')
def move():
    global obstacle_state
    cmd = request.args.get('cmd')
    if not cmd: return "No Command", 400

    # 简单记录非停止指令
    if cmd != 'S':
        add_log(f"[SYS] 执行指令: {cmd}")

    # 1. 检查是否是“前进”指令且处于急刹状态
    if cmd == 'F':
        with obstacle_state["lock"]:
            is_blocked = obstacle_state["emergency_stop"]
        
        if is_blocked:
            # === 触发智能避障逻辑 ===
            add_log("检测到阻挡，开始自动扫描避障...")
            
            # A. 扫描左侧 (Arduino 'J')
            send_to_arduino('J') 
            time.sleep(0.6) 
            # 手动读取一次距离，因为 gpiozero 是基于阈值的，需要具体数值
            dist_left = ultrasonic_sensor.distance * 100
            add_log(f"左侧距离: {dist_left:.1f}cm")
            
            # B. 扫描右侧 (Arduino 'H')
            send_to_arduino('H')
            time.sleep(0.6)
            dist_right = ultrasonic_sensor.distance * 100
            add_log(f"右侧距离: {dist_right:.1f}cm")
            
            # C. 舵机回中 (Arduino 'G')
            send_to_arduino('G')
            time.sleep(0.3)
            
            # D. 决策 (麦克纳姆轮：原地旋转)
            # 哪边空旷就往哪边原地转一小会儿，停下
            if dist_left > MIN_EMERGENCY_DISTANCE and dist_left > dist_right:
                add_log(">> 决定：原地左旋避让")
                send_to_arduino('L') # 原地左转
                time.sleep(0.4)      # 转动时间
                send_to_arduino('S')
                return "AVOIDED LEFT"
                
            elif dist_right > MIN_EMERGENCY_DISTANCE and dist_right >= dist_left:
                add_log(">> 决定：原地右旋避让")
                send_to_arduino('R') # 原地右转
                time.sleep(0.4)      # 转动时间
                send_to_arduino('S')
                return "AVOIDED RIGHT"
                
            else:
                add_log(">> 决定：死胡同，无法避让")
                return "BLOCKED"
        
        else:
            # 路况良好
            send_to_arduino('F')
            return "FORWARD"

    # 2. 后退指令 (B) - 后退能解除软件层面的急刹锁
    elif cmd == 'B':
        with obstacle_state["lock"]:
            if obstacle_state["emergency_stop"]:
                obstacle_state["emergency_stop"] = False
                print("手动后退 -> 解除急刹锁定")
        send_to_arduino('B')
        return "BACKWARD"
    
    else:
        # 为了安全，每次手动操作非前进指令时，最好让舵机回正
        send_to_arduino('G') 
        send_to_arduino(cmd)
        return f"CMD {cmd}"

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True) # Threaded 对 Flask+GPIO 很重要
    finally:
        if ser: ser.close()
import cv2
from ultralytics import YOLO
import requests
import time
import sys
import threading
from flask import Flask, Response

# ================= 配置区域 =================
CAR_SERVER_URL = "http://127.0.0.1:5000/move"
STREAM_PORT = 5001  # 视频流专用端口

FRAME_WIDTH = 640
FRAME_HEIGHT = 480
CENTER_X = FRAME_WIDTH // 2
TOLERANCE = 80 
MAX_HEIGHT_RATIO = 0.6 
MIN_HEIGHT_RATIO = 0.2 

# 默认目标 ID
DEFAULT_CLASS_ID = 0 

# 全局变量（用于线程间共享画面）
output_frame = None
lock = threading.Lock()

# 初始化 Flask (用于视频流)
app = Flask(__name__)

# ===========================================

def send_cmd(cmd):
    try:
        requests.get(f"{CAR_SERVER_URL}?cmd={cmd}", timeout=0.1)
        # print(f">> 发送指令: {cmd}")
    except Exception:
        pass 

def tracker_thread(target_class_id):
    """
    原本的主循环，现在作为一个后台线程运行。
    负责：读取摄像头 -> YOLO 推理 -> 决策控制 -> 更新全局 output_frame
    """
    global output_frame, lock

    print(f"正在加载 YOLOv8n 模型... 目标ID: {target_class_id}", flush=True)
    try:
        model = YOLO('yolov8n.pt')
    except Exception as e:
        print(f"模型加载失败: {e}")
        return

    print("正在打开摄像头...", flush=True)
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(3, FRAME_WIDTH)
    cap.set(4, FRAME_HEIGHT)
    
    INFERENCE_SIZE = 320 
    last_cmd_time = 0
    CMD_INTERVAL = 0.2 

    if not cap.isOpened():
        print("!!! 摄像头打开失败 !!!")
        return

    print(f"=== 视觉跟踪线程已启动 (ID: {target_class_id}) ===", flush=True)

    try:
        while True:
            # 1. 读帧
            try:
                success, frame = cap.read()
                if not success:
                    time.sleep(0.01)
                    continue
            except Exception:
                time.sleep(0.01)
                continue

            # 2. YOLO 推理
            # 降低置信度可以更容易发现目标
            results = model(frame, imgsz=INFERENCE_SIZE, stream=True, conf=0.4, verbose=False)

            target_box = None
            max_area = 0
            
            # 3. 解析结果并绘图
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0]) # 转为整数坐标
                    
                    # --- 绘图逻辑 ---
                    # 无论是不是目标，都画个细框表示看见了
                    # 颜色格式: (B, G, R)
                    if cls_id == target_class_id:
                        # 目标物体：画粗绿色框
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 4)
                        cv2.putText(frame, f"TARGET {cls_id}", (x1, y1 - 10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                        
                        # 记录最大目标用于控制
                        area = (x2 - x1) * (y2 - y1)
                        if area > max_area:
                            max_area = area
                            target_box = (x1, y1, x2, y2)
                    else:
                        # 非目标物体：画细红色框
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)

            # 4. 更新全局画面 (供网页直播)
            with lock:
                output_frame = frame.copy()

            # 5. 控制逻辑 
            current_time = time.time()
            if current_time - last_cmd_time > CMD_INTERVAL:
                if target_box:
                    x1, y1, x2, y2 = target_box
                    box_center_x = (x1 + x2) / 2
                    box_height = y2 - y1
                    
                    if box_center_x < (CENTER_X - TOLERANCE):
                        send_cmd('L')
                    elif box_center_x > (CENTER_X + TOLERANCE):
                        send_cmd('R')
                    else:
                        height_ratio = box_height / FRAME_HEIGHT
                        if height_ratio > MAX_HEIGHT_RATIO:
                            send_cmd('S')
                        elif height_ratio < MIN_HEIGHT_RATIO:
                            send_cmd('F')
                        else:
                            send_cmd('S')
                else:
                    send_cmd('S')
                last_cmd_time = current_time

    except Exception as e:
        print(f"跟踪线程出错: {e}")
    finally:
        cap.release()
        send_cmd('S')

# ================= Flask 视频流部分 =================

def generate():
    """视频流生成器"""
    global output_frame, lock
    while True:
        with lock:
            if output_frame is None:
                continue
            # 将图片编码为 jpg
            (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
            if not flag:
                continue
        
        # 转换为字节流
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
              bytearray(encodedImage) + b'\r\n')

@app.route("/video_feed")
def video_feed():
    """前端 <img> 标签会访问这个地址"""
    return Response(generate(),
                    mimetype = "multipart/x-mixed-replace; boundary=frame")

def main():
    # 解析参数
    target_class_id = DEFAULT_CLASS_ID
    if len(sys.argv) > 1:
        try:
            target_class_id = int(sys.argv[1])
        except ValueError:
            pass
            
    # 1. 启动视觉跟踪线程 (Daemon=True 主程序退出也被杀死)
    t = threading.Thread(target=tracker_thread, args=(target_class_id,))
    t.daemon = True
    t.start()
    
    # 2. 启动 Flask 视频服务器 (阻塞运行)
    # host='0.0.0.0' 允许局域网访问
    print(f"=== 视频流已在端口 {STREAM_PORT} 启动 ===", flush=True)
    # use_reloader=False 防止 Flask 启动两次导致线程混乱
    app.run(host='0.0.0.0', port=STREAM_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
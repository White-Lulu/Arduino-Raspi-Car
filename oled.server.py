import time
import subprocess
import datetime
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106 
from luma.core.render import canvas
from PIL import ImageFont

# 初始化OLED
try:
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial)
    print("OLED 初始化成功。")
except Exception as e:
    print(f"OLED 初始化失败: {e}")
    exit()


def get_system_info(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
    except Exception:
        return "N/A"

def main():
    while True:
        # 收集数据 
        ip_cmd = "hostname -I | cut -d' ' -f1"
        ip_addr = get_system_info(ip_cmd) 
        
        cpu_cmd = "top -bn1 | grep load | awk '{printf \"CPU: %.2f%%\", $(NF-2)}'"
        cpu_load = get_system_info(cpu_cmd) 
        
        mem_cmd = "free -m | awk 'NR==2{printf \"RAM: %s/%sMB\", $3,$2}'"
        mem_usage = get_system_info(mem_cmd) 
        
        disk_cmd = "df -h | awk '$NF==\"/\"{printf \"Disk: %d/%dGB %s\", $3,$2,$5}'"
        disk_usage = get_system_info(disk_cmd) 

        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M:%S")

        # 绘制到屏幕
        with canvas(device) as draw:
            # (x, y) 坐标
            draw.text((0, 0),  f"IP: {ip_addr}", fill="white")
            draw.text((0, 12), f"{cpu_load}", fill="white")
            draw.text((0, 24), f"{mem_usage}", fill="white")
            draw.text((0, 36), f"{disk_usage}", fill="white")
            draw.text((0, 48), f"Time: {current_time}", fill="white")
            
        time.sleep(1) # 每秒刷新一次

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("程序已停止。")
import os
import sys
import time
import signal
import logging
import datetime
import schedule
import subprocess
from logging.handlers import TimedRotatingFileHandler

import paho.mqtt.client as mqtt
from zxtouch.touchtypes import * 
from zxtouch.client import zxtouch

# 设置日志级别
LOGGING_LEVEL = os.environ.get('LOGGING_LEVEL', 'INFO')

# MQTT设置
MQTT_BROKER = os.environ.get('MQTT_BROKER', 'YOUR_MQTT_BROKER')
MQTT_PORT = int(os.environ.get('MQTT_PORT', 21883))
MQTT_TOPIC = "home/doorlock/set"
MQTT_STATE_TOPIC = "home/doorlock/state"
MQTT_CHECK_TOPIC = "home/doorlock/check_status"

# iPhone/ZXTouch设置
IPHONE_IP = os.environ.get('IPHONE_IP', 'YOUR_IPHONE_IP')
ZXTOUCH_PORT = int(os.environ.get('ZXTOUCH_PORT', 6000))

# iPhone SSH认证设置
IPHONE_SSH_PASSWORD = os.environ.get('IPHONE_SSH_PASSWORD', '')

# Dim模式设置
DIM_ENABLE_COMMAND = "activator send switch-on.com.thomasfinch.dim"
DIM_DISABLE_COMMAND = "activator send switch-off.com.thomasfinch.dim"

# APP启动设置
APP_BUNDLE_ID = "com.ykkap.SmartControlKey"
APP_LAUNCH_COMMAND = f"uiopen -b {APP_BUNDLE_ID}"
APP_PROCESS_NAME = "Alpha Lock"

# 休眠控制设置
ENABLE_SLEEP_MANAGEMENT = os.environ.get('ENABLE_SLEEP_MANAGEMENT', 'true').lower() == 'true'
SLEEP_COMMAND = "activator send libactivator.system.sleepbutton"
WAKEUP_COMMAND = "activator send libactivator.system.homebutton"
UNLOCK_COMMAND = "activator send libactivator.lockscreen.toggle"

# 截图设置
SCREENSHOT_COMMAND = "activator send libactivator.system.take-screenshot"

# 坐标设置 (根据iPhone实际界面确定)
COLOR_CHECK_COORDS = (71, 305)        # 锁定状态图标检测点(锁体左侧)
UNLOCK_COORDS = (515, 960)            # 红色"解錠"按键坐标(中央处)
LOCK_COORDS = (230, 960)              # 绿色"施錠"按键坐标(中央处)
RELEASE_SLEEP_COORDS = (375, 1130)    # "スリープモード解除"按键坐标(中央处)
SLEEP_CHECK_COORDS = (215, 1120)      # "スリープモード解除"按键颜色检测点(左侧)
AUTHENTICATION_CHECK_COORDS = (375, 200)  # 认证中灰色遮罩层检测点

# ==================== 正常模式颜色定义 ====================
# 门锁状态检测颜色 - 坐标 (71, 305)
NORMAL_UNLOCK_COLOR = (195, 23, 45)          # 未锁定状态的红色
NORMAL_LOCKED_COLOR = (0, 168, 135)          # 锁定状态的绿色  
NORMAL_UNLINKED_COLOR = (130, 130, 130)      # 未连接状态的灰色

# APP睡眠状态检测颜色 - 坐标 (215, 1120)
NORMAL_SLEEP_MODE_COLOR = (206, 14, 45)      # APP睡眠状态的红色（推测与解锁按钮相近）
NORMAL_NON_SLEEP_COLOR = (130, 130, 130)     # APP非睡眠状态的灰色（推测与未连接相近）

# 认证状态检测颜色 - 坐标 (375, 200)
NORMAL_AUTHENTICATING_COLOR = (0, 66, 91)    # 认证中遮罩层颜色
NORMAL_NON_AUTHENTICATING_COLOR = (1, 132, 186)  # 非认证状态颜色

# ==================== Dim模式颜色定义 ====================
# 门锁状态检测颜色 - 坐标 (71, 305)
DIM_UNLOCK_COLOR = (39, 5, 9)                # Dim模式：未锁定状态的暗红色
DIM_LOCKED_COLOR = (0, 34, 27)               # Dim模式：锁定状态的暗绿色
DIM_UNLINKED_COLOR = (26, 26, 26)            # Dim模式：未连接状态的深灰色

# APP睡眠状态检测颜色 - 坐标 (215, 1120)
DIM_SLEEP_MODE_COLOR = (41, 3, 9)            # Dim模式：APP睡眠状态的暗红色
DIM_NON_SLEEP_COLOR = (26, 26, 26)           # Dim模式：APP非睡眠状态的深灰色

# 认证状态检测颜色 - 坐标 (375, 200)
DIM_AUTHENTICATING_COLOR = (0, 13, 18)       # Dim模式：认证中遮罩层颜色
DIM_NON_AUTHENTICATING_COLOR = (0, 26, 37)   # Dim模式：非认证状态颜色

# 颜色匹配容差
COLOR_TOLERANCE = 10

# 定时检查门锁状态时间
START_CHECK_STATUS_HOUR = int(os.environ.get('START_CHECK_STATUS_HOUR', 7))
STOP_CHECK_STATUS_HOUR = int(os.environ.get('STOP_CHECK_STATUS_HOUR', 22))
CHECK_INTERVAL_MINUTES = 30

# 认证等待设置
AUTHENTICATION_TIMEOUT = 6  # 认证最长等待时间(秒)
AUTHENTICATION_CHECK_INTERVAL = 0.5  # 认证状态检查间隔(秒)

# 全局变量
mqtt_client = None
zx_device = None

def setup_logging():
    """配置日志系统"""
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'), exist_ok=True)
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'doorlock_iphone.log')
    
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 创建 TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = '%Y%m%d.log'
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOGGING_LEVEL)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(LOGGING_LEVEL)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(LOGGING_LEVEL)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

def execute_ssh_command(command, timeout=10):
    """通过SSH在iPhone上执行命令（使用密码认证）"""
    if not IPHONE_SSH_PASSWORD:
        logging.error("IPHONE_SSH_PASSWORD is not set")
        return False, "", "IPHONE_SSH_PASSWORD is not set"

    try:
        # 使用sshpass进行密码认证
        ssh_cmd = [
            "sshpass", "-p", IPHONE_SSH_PASSWORD,
            "ssh",
            "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=2",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"root@{IPHONE_IP}",
            command
        ]
        
        logging.info(f"通过SSH执行命令: {' '.join(ssh_cmd[:-2])} [命令已隐藏]")
        result = subprocess.run(ssh_cmd, timeout=timeout, 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            logging.info(f"SSH命令执行成功: {result.stdout.strip()}")
            return True, result.stdout.strip(), result.stderr.strip()
        else:
            logging.error(f"SSH命令执行失败，返回码: {result.returncode}")
            logging.error(f"错误输出: {result.stderr.strip()}")
            return False, result.stdout.strip(), result.stderr.strip()
            
    except subprocess.TimeoutExpired:
        logging.error("SSH命令执行超时")
        return False, "", "SSH命令超时"
    except FileNotFoundError as e:
        if "sshpass" in str(e):
            logging.error("未找到sshpass命令，请安装: brew install sshpass (Mac) 或 apt-get install sshpass (Linux)")
            return False, "", "缺少sshpass工具"
        else:
            logging.error(f"SSH命令未找到: {e}")
            return False, "", str(e)
    except Exception as e:
        logging.error(f"执行SSH命令时出错: {e}")
        return False, "", str(e)

def take_screenshot(reason="debug"):
    """在iPhone上截图用于调试"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        logging.info(f"正在截图，原因: {reason}，时间戳: {timestamp}")
        
        success, stdout, stderr = execute_ssh_command(SCREENSHOT_COMMAND)
        
        if success:
            logging.info(f"截图成功，原因: {reason}")
            return True
        else:
            logging.error(f"截图失败，原因: {reason}，错误: {stderr}")
            return False
            
    except Exception as e:
        logging.error(f"截图时出错: {e}")
        return False

def execute_activator_command(command):
    """执行activator命令（通过SSH）"""
    success, stdout, stderr = execute_ssh_command(command)
    return success

def enable_dim_mode():
    """启用Dim模式（极暗模式）"""
    logging.info("正在启用Dim模式...")
    if execute_activator_command(DIM_ENABLE_COMMAND):
        logging.info("Dim模式已启用")
        return True
    else:
        logging.error("启用Dim模式失败")
        return False

def disable_dim_mode():
    """关闭Dim模式"""
    logging.info("正在关闭Dim模式...")
    if execute_activator_command(DIM_DISABLE_COMMAND):
        logging.info("Dim模式已关闭")
        return True
    else:
        logging.error("关闭Dim模式失败")
        return False

def is_app_running():
    """检查门锁APP是否正在运行（通过SSH）"""
    try:
        command = f'ps -ef | grep "{APP_PROCESS_NAME}"'
        success, stdout, stderr = execute_ssh_command(command)
        
        if not success:
            logging.error("检查APP运行状态时SSH执行失败")
            return False
        
        # 过滤掉grep进程本身
        lines = [line for line in stdout.split('\n') 
                if APP_PROCESS_NAME in line and 'grep' not in line]
        
        if lines:
            logging.info(f"门锁APP正在运行: {lines[0].strip()}")
            return True
        else:
            logging.info("门锁APP未运行")
            return False
    except Exception as e:
        logging.error(f"检查APP运行状态时出错: {e}")
        return False

def launch_app():
    """启动门锁APP（通过SSH）"""
    try:
        logging.info(f"正在启动门锁APP: {APP_BUNDLE_ID}")
        success, stdout, stderr = execute_ssh_command(APP_LAUNCH_COMMAND)
        
        if success:
            logging.info(f"APP启动命令执行成功: {stdout}")
            
            # 等待APP启动
            time.sleep(5)
            
            # 验证APP是否成功启动
            if is_app_running():
                logging.info("门锁APP启动成功")
                return True
            else:
                logging.warning("APP启动命令执行成功，但进程检查未发现APP运行")
                return False
        else:
            logging.error(f"启动APP失败: {stderr}")
            return False
            
    except Exception as e:
        logging.error(f"启动APP时出错: {e}")
        return False

def check_screen_state():
    """检查iPhone屏幕状态"""
    try:
        # 尝试获取多个坐标的颜色来判断屏幕状态
        test_coords = [(100, 100), (200, 200), (300, 300)]
        colors = []
        
        for x, y in test_coords:
            color = get_pixel_color(x, y)
            if color is not None:
                colors.append(color)
        
        if not colors:
            logging.warning("无法获取任何坐标的颜色，假设为休眠状态")
            return "sleep"
        
        # 检查是否所有颜色都是(0,0,0)，表示休眠状态
        all_black = all(color == (0, 0, 0) for color in colors)
        if all_black:
            logging.info("检测到休眠状态（所有颜色为黑色）")
            return "sleep"
        
        # 如果能获取到颜色且不全是黑色，说明屏幕是亮的
        logging.debug(f"检测到屏幕唤醒状态，颜色样本: {colors}")
        return "awake"
        
    except Exception as e:
        logging.error(f"检查屏幕状态时出错: {e}")
        return "unknown"

def wake_up_screen():
    """唤醒iPhone屏幕"""
    try:
        screen_state = check_screen_state()
        
        if screen_state == "sleep":
            logging.info("屏幕处于休眠状态，正在唤醒...")
            
            # 使用Home键唤醒
            if execute_activator_command(WAKEUP_COMMAND):
                time.sleep(2)  # 等待屏幕唤醒
                
                # 验证是否成功唤醒
                new_state = check_screen_state()
                if new_state == "awake":
                    logging.info("屏幕成功唤醒")
                    return True
                else:
                    logging.warning("屏幕唤醒可能失败，再次尝试...")
                    # 再次尝试用sleepbutton
                    execute_activator_command(SLEEP_COMMAND)
                    time.sleep(2)
                    final_state = check_screen_state()
                    if final_state == "awake":
                        logging.info("屏幕成功唤醒（第二次尝试）")
                        return True
                    else:
                        logging.error("屏幕唤醒失败")
                        return False
            else:
                logging.error("执行唤醒命令失败")
                return False
        else:
            logging.debug("屏幕已处于唤醒状态")
            return True
            
    except Exception as e:
        logging.error(f"唤醒屏幕时出错: {e}")
        return False

def smart_unlock_screen():
    """智能解锁屏幕：只在休眠状态时才执行唤醒+解锁"""
    try:
        screen_state = check_screen_state()
        
        if screen_state == "sleep":
            logging.info("检测到屏幕处于休眠状态，正在唤醒并解锁...")
            
            # 先唤醒屏幕
            if execute_activator_command(WAKEUP_COMMAND):
                time.sleep(2)  # 等待屏幕唤醒
                
                # 验证唤醒是否成功
                new_state = check_screen_state()
                if new_state == "awake":
                    logging.info("屏幕已唤醒，正在解锁...")
                    # 执行解锁
                    if execute_activator_command(UNLOCK_COMMAND):
                        time.sleep(1)  # 等待解锁完成
                        logging.info("屏幕解锁完成")
                        return True
                    else:
                        logging.error("解锁命令执行失败")
                        return False
                else:
                    logging.warning("屏幕唤醒可能失败，尝试使用sleepbutton切换")
                    # 备选方案：用sleepbutton切换
                    execute_activator_command(SLEEP_COMMAND)
                    time.sleep(2)
                    final_state = check_screen_state()
                    if final_state == "awake":
                        logging.info("通过sleepbutton成功唤醒屏幕")
                        return True
                    else:
                        logging.error("所有唤醒尝试均失败")
                        return False
            else:
                logging.error("执行唤醒命令失败")
                return False
        else:
            logging.info("屏幕已处于唤醒状态，无需解锁操作")
            return True
            
    except Exception as e:
        logging.error(f"智能解锁屏幕时出错: {e}")
        return False

def sleep_screen():
    """让iPhone进入休眠状态"""
    try:
        logging.info("正在让iPhone进入休眠状态...")
        if execute_activator_command(SLEEP_COMMAND):
            time.sleep(2)  # 等待进入休眠
            
            # 验证是否成功进入休眠
            screen_state = check_screen_state()
            if screen_state == "sleep":
                logging.info("iPhone成功进入休眠状态")
                return True
            else:
                logging.warning("iPhone可能未成功进入休眠状态")
                return False
        else:
            logging.error("执行休眠命令失败")
            return False
            
    except Exception as e:
        logging.error(f"让iPhone休眠时出错: {e}")
        return False

def connect_zxtouch():
    """连接到ZXTouch服务"""
    global zx_device
    try:
        zx_device = zxtouch(IPHONE_IP, ZXTOUCH_PORT)
        logging.info(f"成功连接到ZXTouch服务: {IPHONE_IP}:{ZXTOUCH_PORT}")
        
        # 获取屏幕尺寸验证连接
        screen_size = zx_device.get_screen_size()
        logging.info(f"iPhone屏幕尺寸: {screen_size}")
        return True
    except Exception as e:
        logging.error(f"连接ZXTouch失败: {e}")
        zx_device = None
        return False

def get_pixel_color(x, y):
    """获取指定坐标的颜色值"""
    global zx_device
    
    # 确保设备连接
    if zx_device is None:
        logging.error("ZXTouch设备未连接")
        if not connect_zxtouch():
            logging.error("重新连接失败")
            return None
    
    try:
        result = zx_device.pick_color(x, y)
        if result[0]:  # 成功获取颜色
            r = int(result[1]['red'])
            g = int(result[1]['green']) 
            b = int(result[1]['blue'])
            return (r, g, b)
        else:
            logging.error(f"无法获取坐标({x}, {y})的颜色")
            return None
    except Exception as e:
        logging.error(f"获取颜色时出错: {e}")
        return None

def tap_screen(x, y):
    """点击屏幕指定坐标"""
    global zx_device
    
    # 确保设备连接
    if zx_device is None:
        logging.error("ZXTouch设备未连接")
        if not connect_zxtouch():
            logging.error("重新连接失败")
            return False
    
    try:
        logging.info(f"点击屏幕坐标: ({x}, {y})")
        
        # 使用ZXTouch常量进行触摸操作
        zx_device.touch(TOUCH_DOWN, 1, x, y)  # 按下
        time.sleep(0.1)                       # 100ms延迟
        zx_device.touch(TOUCH_UP, 1, x, y)    # 抬起
        
        logging.info(f"成功点击屏幕坐标: ({x}, {y})")
        return True
    except Exception as e:
        logging.error(f"点击屏幕失败: {e}")
        return False

def color_matches(color1, color2, tolerance):
    """检查两个颜色是否在容差范围内匹配"""
    if color1 is None or color2 is None:
        return False
    return all(abs(c1 - c2) <= tolerance for c1, c2 in zip(color1[:3], color2[:3]))

def dual_color_matches(pixel_color, normal_color, dim_color, tolerance):
    """
    双颜色集匹配：同时检查正常模式和Dim模式的颜色
    
    Args:
        pixel_color: 实际获取的像素颜色
        normal_color: 正常模式下的目标颜色
        dim_color: Dim模式下的目标颜色
        tolerance: 颜色匹配容差
    
    Returns:
        bool: 如果匹配任一颜色集则返回True
    """
    if pixel_color is None:
        return False
    
    # 检查是否匹配正常模式颜色
    normal_match = color_matches(pixel_color, normal_color, tolerance)
    # 检查是否匹配Dim模式颜色
    dim_match = color_matches(pixel_color, dim_color, tolerance)
    
    if normal_match:
        logging.debug(f"颜色匹配成功：正常模式 - 像素颜色{pixel_color} 匹配 {normal_color}")
        return True
    elif dim_match:
        logging.debug(f"颜色匹配成功：Dim模式 - 像素颜色{pixel_color} 匹配 {dim_color}")
        return True
    else:
        logging.debug(f"颜色匹配失败 - 像素颜色{pixel_color} 不匹配正常模式{normal_color}或Dim模式{dim_color}")
        return False

def check_authentication_status():
    """检查是否正在认证中（支持双颜色集）"""
    try:
        pixel_color = get_pixel_color(*AUTHENTICATION_CHECK_COORDS)
        if pixel_color is None:
            logging.warning("无法获取认证检查坐标的颜色，假设非认证状态")
            return False
            
        logging.debug(f"认证检查坐标{AUTHENTICATION_CHECK_COORDS}的颜色: {pixel_color}")
        
        # 使用双颜色集检查是否匹配认证中的遮罩层颜色
        is_authenticating = dual_color_matches(
            pixel_color, 
            NORMAL_AUTHENTICATING_COLOR, 
            DIM_AUTHENTICATING_COLOR, 
            COLOR_TOLERANCE
        )
        
        if is_authenticating:
            logging.info("检测到正在认证中（灰色遮罩层）")
        else:
            logging.debug("未检测到认证状态")
            
        return is_authenticating
    except Exception as e:
        logging.error(f"检查认证状态时出错: {e}")
        return False

def wait_for_authentication_complete():
    """智能等待认证完成"""
    logging.info("等待认证完成...")
    start_time = time.time()
    
    while time.time() - start_time < AUTHENTICATION_TIMEOUT:
        if not check_authentication_status():
            elapsed_time = time.time() - start_time
            logging.info(f"认证已完成，耗时: {elapsed_time:.1f}秒")
            return True
        
        logging.debug(f"认证进行中，继续等待... ({time.time() - start_time:.1f}s)")
        time.sleep(AUTHENTICATION_CHECK_INTERVAL)
    
    # 超时
    logging.warning(f"等待认证完成超时({AUTHENTICATION_TIMEOUT}秒)")
    return False

def check_sleep_mode():
    """检查门锁是否处于睡眠模式（支持双颜色集）"""
    try:
        # 获取睡眠检查坐标的颜色
        pixel_color = get_pixel_color(*SLEEP_CHECK_COORDS)
        if pixel_color is None:
            logging.warning("无法获取睡眠检查坐标的颜色，假设非睡眠状态")
            return False
            
        logging.debug(f"睡眠检查坐标{SLEEP_CHECK_COORDS}的颜色: {pixel_color}")
        
        # 使用双颜色集检查是否为睡眠模式颜色（红色）
        is_sleep = dual_color_matches(
            pixel_color,
            NORMAL_SLEEP_MODE_COLOR,
            DIM_SLEEP_MODE_COLOR,
            COLOR_TOLERANCE
        )
        
        if is_sleep:
            logging.info("检测到门锁处于睡眠模式")
        else:
            logging.debug("门锁未处于睡眠模式")
            
        return is_sleep
    except Exception as e:
        logging.error(f"检查睡眠模式时出错: {e}")
        return False

def release_sleep_if_needed():
    """根据需要解除睡眠模式"""
    if check_sleep_mode():
        logging.info("门锁处于睡眠模式，正在解除...")
        tap_screen(*RELEASE_SLEEP_COORDS)
        time.sleep(1)  # 等待解除睡眠模式完成
        logging.info("睡眠模式已解除")
        return True
    else:
        logging.debug("门锁未处于睡眠模式，跳过解除睡眠操作")
        return False

def check_lock_status():
    """检查门锁状态（支持双颜色集）"""
    try:
        # 第一次检查，如果处于睡眠则解除
        release_sleep_if_needed()
        
        # 获取颜色检查坐标的颜色
        pixel_color = get_pixel_color(*COLOR_CHECK_COORDS)
        if pixel_color is None:
            return "unknown"
            
        logging.info(f"在坐标{COLOR_CHECK_COORDS}检测到颜色: {pixel_color}")

        # 使用双颜色集匹配检测未锁定状态（红色）
        if dual_color_matches(pixel_color, NORMAL_UNLOCK_COLOR, DIM_UNLOCK_COLOR, COLOR_TOLERANCE):
            logging.info("检测到未锁定状态（红色）")
            return "unlocked"
        
        # 使用双颜色集匹配检测锁定状态（绿色）
        elif dual_color_matches(pixel_color, NORMAL_LOCKED_COLOR, DIM_LOCKED_COLOR, COLOR_TOLERANCE):
            logging.info("检测到锁定状态（绿色）")
            return "locked"
        
        # 使用双颜色集匹配检测未连接状态（灰色）
        elif dual_color_matches(pixel_color, NORMAL_UNLINKED_COLOR, DIM_UNLINKED_COLOR, COLOR_TOLERANCE):
            # 检测到灰色，需要区分是睡眠还是真的未连接
            logging.info("检测到灰色，正在确认是睡眠还是未连接...")
            
            # 检查是否处于睡眠模式
            if check_sleep_mode():
                logging.info("确认为睡眠状态，正在解除睡眠并重新检测...")
                # 强制解除睡眠 
                tap_screen(*RELEASE_SLEEP_COORDS)
                time.sleep(1.5)  # 等待解除睡眠完成
                
                # 重新检测状态
                pixel_color_after = get_pixel_color(*COLOR_CHECK_COORDS)
                if pixel_color_after is None:
                    return "unknown"
                    
                logging.info(f"解除睡眠后重新检测颜色: {pixel_color_after}")
                
                # 再次使用双颜色集匹配
                if dual_color_matches(pixel_color_after, NORMAL_UNLOCK_COLOR, DIM_UNLOCK_COLOR, COLOR_TOLERANCE):
                    logging.info("解除睡眠后检测到未锁定状态（红色）")
                    return "unlocked"
                elif dual_color_matches(pixel_color_after, NORMAL_LOCKED_COLOR, DIM_LOCKED_COLOR, COLOR_TOLERANCE):
                    logging.info("解除睡眠后检测到锁定状态（绿色）")
                    return "locked"
                elif dual_color_matches(pixel_color_after, NORMAL_UNLINKED_COLOR, DIM_UNLINKED_COLOR, COLOR_TOLERANCE):
                    logging.warning("解除睡眠后仍为灰色，确认为未连接状态")
                    return "unlinked"
                else:
                    logging.warning(f"解除睡眠后无法匹配颜色: {pixel_color_after}")
                    return "unknown"
            else:
                # 不是睡眠状态，确实是未连接
                logging.warning("确认为未连接状态（灰色）")
                return "unlinked"
        else:
            logging.warning(f"无法匹配颜色: {pixel_color}")
            return "unknown"
    except Exception as e:
        logging.error(f"检查锁状态时出错: {e}")
        return "error"

def control_lock(action, client, retry=3):
    """控制门锁的锁定或解锁 - 优化认证状态处理"""
    try:
        # 智能解锁：只在休眠状态时才执行解锁操作
        if not smart_unlock_screen():
            logging.warning("无法智能解锁屏幕，但继续尝试门锁操作")
        
        # 优化：只在需要时解除睡眠模式
        sleep_released = release_sleep_if_needed()
        
        # 选择对应的按键坐标
        coords = UNLOCK_COORDS if action == "unlock" else LOCK_COORDS
        
        # 点击按键
        if not tap_screen(*coords):
            logging.error(f"点击{action}按键失败")
            client.publish(MQTT_STATE_TOPIC, "ERROR")
            return
            
        logging.info(f"执行{action}操作")
        
        # 初始等待1秒
        time.sleep(1)
        
        # 检查是否在认证中
        if check_authentication_status():
            logging.info("检测到正在认证中，等待认证完成...")
            if not wait_for_authentication_complete():
                logging.warning("等待认证完成超时")
                # 即使超时也继续检查状态，可能认证已经完成
        
        # 检查操作结果
        status = check_lock_status()
        
        # 验证操作是否成功
        if (action == "unlock" and status == "unlocked") or (action == "lock" and status == "locked"):
            logging.info(f"{action}操作成功")
            client.publish(MQTT_STATE_TOPIC, status.upper())
            return
        
        # 操作未成功，进行重试
        logging.warning(f"{action}操作未成功，当前状态: {status}")
        if retry > 0:
            # 截图用于调试
            take_screenshot(f"{action}_retry_attempt_{4-retry}")
            
            # 重试前先确认不在认证中
            if check_authentication_status():
                logging.info("重试前检测到仍在认证中，等待认证完成...")
                wait_for_authentication_complete()
            
            logging.warning(f"{action}操作未成功,重试中...")
            time.sleep(2)  # 重试前稍等
            control_lock(action, client, retry - 1)  # 重试
        else:
            # 最终失败也截图
            take_screenshot(f"{action}_final_failure")
            logging.error(f"{action}操作失败!")
            client.publish(MQTT_STATE_TOPIC, "UNKNOWN")
            
    except Exception as e:
        logging.error(f"控制门锁时出错: {e}")
        # 发生异常时也截图
        take_screenshot(f"{action}_exception")
        client.publish(MQTT_STATE_TOPIC, "ERROR")

def check_and_publish_status(client):
    """检查锁状态并发布到MQTT"""
    try:
        # 在检查状态前智能解锁（只在休眠时才执行）
        if not smart_unlock_screen():
            logging.warning("无法智能解锁屏幕，但继续尝试检查门锁状态")
        
        status = check_lock_status()
        if status == "unlocked":
            logging.info("检查结果: 门锁已解锁")
            client.publish(MQTT_STATE_TOPIC, "UNLOCKED")
        elif status == "locked":
            logging.info("检查结果: 门锁已锁定")
            client.publish(MQTT_STATE_TOPIC, "LOCKED")
        elif status == "unlinked":
            logging.warning("检查结果: 门锁未连接")
            client.publish(MQTT_STATE_TOPIC, "UNLINKED")
        else:
            logging.warning("检查结果: 无法确定门锁状态")
            client.publish(MQTT_STATE_TOPIC, "UNKNOWN")
        return status
    except Exception as e:
        logging.error(f"检查并发布状态时出错: {e}")
        client.publish(MQTT_STATE_TOPIC, "ERROR")
        return "error"

def periodic_status_check():
    """定期检查门锁状态的函数"""
    current_time = datetime.datetime.now().time()
    # 在特定时间段内检查门锁状态
    if datetime.time(START_CHECK_STATUS_HOUR, 0) <= current_time <= datetime.time(STOP_CHECK_STATUS_HOUR, 0):
        check_and_publish_status(mqtt_client)
    else:
        # 在非工作时间段，如果启用了休眠管理，让iPhone进入休眠
        if ENABLE_SLEEP_MANAGEMENT:
            logging.info("当前处于非工作时间段，让iPhone进入休眠状态")
            sleep_screen()

def schedule_tasks():
    """安排所有定时任务"""
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(periodic_status_check)

def run_pending_and_get_next_run():
    """检查到下一个定时任务的时长"""
    schedule.run_pending()
    return schedule.idle_seconds()

# MQTT回调函数
def on_connect(client, userdata, flags, rc, properties=None):
    """MQTT连接成功后的回调函数"""
    logging.info(f"MQTT连接成功，返回码: {rc}")
    client.subscribe(MQTT_TOPIC)
    client.subscribe(MQTT_CHECK_TOPIC)

def on_message(client, userdata, msg):
    """接收到MQTT消息后的回调函数"""
    logging.info(f"收到MQTT消息: {msg.topic} {str(msg.payload)}")
    if msg.topic == MQTT_TOPIC:
        if msg.payload == b"UNLOCK":
            control_lock("unlock", client)
        elif msg.payload == b"LOCK":
            control_lock("lock", client)
    elif msg.topic == MQTT_CHECK_TOPIC:
        check_and_publish_status(client)

def signal_handler(signum, frame):
    """处理终止信号"""
    signal_name = signal.Signals(signum).name
    logging.info(f"收到终止信号 {signal_name}，程序正在关闭...")
    
    # 关闭Dim模式
    logging.info("正在关闭Dim模式...")
    disable_dim_mode()
    
    # 清理 MQTT 连接
    if mqtt_client:
        try:
            mqtt_client.publish(MQTT_STATE_TOPIC, "OFFLINE")
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            logging.info("MQTT 连接已关闭")
        except Exception as e:
            logging.error(f"关闭 MQTT 连接时发生错误: {e}")
    
    logging.info("程序已完全关闭")
    sys.exit(0)

def initialize_system():
    """系统初始化"""
    # 启用Dim模式
    logging.info("系统初始化开始...")
    if not enable_dim_mode():
        logging.warning("启用Dim模式失败，但继续初始化")
    
    # 连接ZXTouch
    if not connect_zxtouch():
        logging.error("无法连接到iPhone的ZXTouch服务!")
        # 即使ZXTouch连接失败，也要关闭Dim模式
        disable_dim_mode()
        return False
    
    # 检查并启动门锁APP
    if not is_app_running():
        logging.info("门锁APP未运行，正在启动...")
        if not launch_app():
            logging.error("启动门锁APP失败!")
            # 不要因为APP启动失败而退出，可能是检测问题
            logging.warning("继续初始化，但门锁功能可能受影响")
    else:
        logging.info("门锁APP已在运行")
    
    # 初始化时智能解锁（只在休眠状态时才执行）
    if not smart_unlock_screen():
        logging.warning("初始化时智能解锁失败，但继续启动")
    
    logging.info("iPhone门锁控制系统初始化完成")
    return True

# 调试功能
def debug_mode():
    """调试模式：帮助确定正确的坐标和颜色"""
    logging.info("进入调试模式...")
    
    if not connect_zxtouch():
        logging.error("调试模式启动失败: 无法连接ZXTouch")
        return
    
    print(f"\n=== iPhone门锁坐标调试模式（支持Dim模式双颜色集） ===")
    print(f"已连接到: {IPHONE_IP}:{ZXTOUCH_PORT}")
    print(f"ZXTouch设备状态: {zx_device}")
    print("1. 获取门锁状态坐标颜色")
    print("2. 点击解锁按键坐标") 
    print("3. 点击锁定按键坐标")
    print("4. 点击解除睡眠按键坐标")
    print("5. 获取睡眠状态坐标颜色")
    print("6. 测试睡眠检查逻辑（双颜色集）")
    print("7. 获取认证状态坐标颜色")
    print("8. 测试认证状态检测（双颜色集）")
    print("9. 测试Dim模式开关")
    print("10. 测试APP启动检测")
    print("11. 测试屏幕状态检测")
    print("12. 测试屏幕唤醒/休眠")
    print("13. 测试截图功能")
    print("14. 测试门锁状态检测（双颜色集）")  # 新增
    print("15. 自定义坐标测试")
    print("0. 退出调试模式")
    
    while True:
        try:
            choice = input("\n请选择操作 (0-15): ").strip()
            
            if choice == "1":
                color = get_pixel_color(*COLOR_CHECK_COORDS)
                print(f"检查坐标 {COLOR_CHECK_COORDS} 的颜色: {color}")
                if color:
                    # 测试双颜色集匹配
                    print(f"\n双颜色集匹配测试:")
                    unlock_match = dual_color_matches(color, NORMAL_UNLOCK_COLOR, DIM_UNLOCK_COLOR, COLOR_TOLERANCE)
                    locked_match = dual_color_matches(color, NORMAL_LOCKED_COLOR, DIM_LOCKED_COLOR, COLOR_TOLERANCE)
                    unlinked_match = dual_color_matches(color, NORMAL_UNLINKED_COLOR, DIM_UNLINKED_COLOR, COLOR_TOLERANCE)
                    print(f"  匹配未锁定状态: {unlock_match}")
                    print(f"  匹配锁定状态: {locked_match}")
                    print(f"  匹配未连接状态: {unlinked_match}")
                
            elif choice == "2":
                print(f"将点击解锁按键坐标: {UNLOCK_COORDS}")
                success = tap_screen(*UNLOCK_COORDS)
                print(f"点击结果: {'成功' if success else '失败'}")
                
            elif choice == "3":
                print(f"将点击锁定按键坐标: {LOCK_COORDS}")
                success = tap_screen(*LOCK_COORDS)
                print(f"点击结果: {'成功' if success else '失败'}")
                
            elif choice == "4":
                print(f"将点击解除睡眠按键坐标: {RELEASE_SLEEP_COORDS}")
                success = tap_screen(*RELEASE_SLEEP_COORDS)
                print(f"点击结果: {'成功' if success else '失败'}")
                
            elif choice == "5":
                color = get_pixel_color(*SLEEP_CHECK_COORDS)
                print(f"睡眠检查坐标 {SLEEP_CHECK_COORDS} 的颜色: {color}")
                if color:
                    # 测试双颜色集匹配
                    is_sleep = dual_color_matches(color, NORMAL_SLEEP_MODE_COLOR, DIM_SLEEP_MODE_COLOR, COLOR_TOLERANCE)
                    print(f"双颜色集匹配结果 - 是否为睡眠模式颜色: {is_sleep}")
                
            elif choice == "6":
                print("正在测试睡眠检查逻辑（使用双颜色集）...")
                is_sleep = check_sleep_mode()
                print(f"睡眠模式检测结果: {is_sleep}")
                if is_sleep:
                    print("正在执行解除睡眠...")
                    release_sleep_if_needed()
                else:
                    print("无需解除睡眠")
                    
            elif choice == "7":
                color = get_pixel_color(*AUTHENTICATION_CHECK_COORDS)
                print(f"认证检查坐标 {AUTHENTICATION_CHECK_COORDS} 的颜色: {color}")
                if color:
                    # 测试双颜色集匹配
                    is_auth = dual_color_matches(color, NORMAL_AUTHENTICATING_COLOR, DIM_AUTHENTICATING_COLOR, COLOR_TOLERANCE)
                    print(f"双颜色集匹配结果 - 是否为认证中颜色: {is_auth}")
                
            elif choice == "8":
                print("正在测试认证状态检测（使用双颜色集）...")
                is_authenticating = check_authentication_status()
                print(f"认证状态检测结果: {is_authenticating}")
                
            elif choice == "9":
                print("=== Dim模式测试 ===")
                print("1. 启用Dim模式")
                print("2. 关闭Dim模式")
                sub_choice = input("请选择操作 (1-2): ").strip()
                if sub_choice == "1":
                    success = enable_dim_mode()
                    print(f"启用Dim模式: {'成功' if success else '失败'}")
                elif sub_choice == "2":
                    success = disable_dim_mode()
                    print(f"关闭Dim模式: {'成功' if success else '失败'}")
                else:
                    print("无效选择，请输入 1 或 2")
                    
            elif choice == "10":
                print("=== APP启动检测测试 ===")
                is_running = is_app_running()
                print(f"APP运行状态: {'运行中' if is_running else '未运行'}")
                if not is_running:
                    print("1. 启动APP")
                    print("2. 跳过")
                    launch_choice = input("请选择操作 (1-2): ").strip()
                    if launch_choice == '1':
                        success = launch_app()
                        print(f"启动APP: {'成功' if success else '失败'}")
                    elif launch_choice == '2':
                        print("跳过启动APP")
                    else:
                        print("无效选择，请输入 1 或 2")
                        
            elif choice == "11":
                print("=== 屏幕状态检测测试 ===")
                screen_state = check_screen_state()
                print(f"屏幕状态: {screen_state}")
                
            elif choice == "12":
                print("=== 屏幕唤醒/休眠测试 ===")
                print("1. 唤醒屏幕")
                print("2. 休眠屏幕") 
                print("3. 智能解锁屏幕（只在休眠时执行）")
                sub_choice = input("请选择操作 (1-3): ").strip()
                if sub_choice == "1":
                    success = wake_up_screen()
                    print(f"唤醒屏幕: {'成功' if success else '失败'}")
                elif sub_choice == "2":
                    success = sleep_screen()
                    print(f"休眠屏幕: {'成功' if success else '失败'}")
                elif sub_choice == "3":
                    success = smart_unlock_screen()
                    print(f"智能解锁屏幕: {'成功' if success else '失败'}")
                else:
                    print("无效选择，请输入 1, 2 或 3")
                
            elif choice == "13":
                print("=== 截图功能测试 ===")
                success = take_screenshot("debug_test")
                print(f"截图测试: {'成功' if success else '失败'}")
                if success:
                    print("截图已保存到iPhone相册，可以在相册中查看")
            
            elif choice == "14":  # 新增：测试完整的门锁状态检测
                print("=== 门锁状态检测测试（双颜色集） ===")
                status = check_lock_status()
                print(f"门锁状态检测结果: {status}")
                print("状态说明:")
                print("  - unlocked: 未锁定（红色）")
                print("  - locked: 已锁定（绿色）")
                print("  - unlinked: 未连接（灰色）")
                print("  - unknown: 无法识别")
                print("  - error: 检测出错")
                
            elif choice == "15":
                x = int(input("请输入X坐标: "))
                y = int(input("请输入Y坐标: "))
                print("1. 获取颜色")
                print("2. 点击坐标")
                action = input("请选择操作 (1-2): ").strip()
                
                if action == "1":
                    color = get_pixel_color(x, y)
                    print(f"坐标 ({x}, {y}) 的颜色: {color}")
                elif action == "2":
                    success = tap_screen(x, y)
                    print(f"点击坐标 ({x}, {y}) 结果: {'成功' if success else '失败'}")
                else:
                    print("无效操作，请输入 1 或 2")
                    
            elif choice == "0":
                print("退出调试模式")
                break
                
            else:
                print("无效选择，请输入: 0-15")
                
        except KeyboardInterrupt:
            print("\n退出调试模式")
            break
        except Exception as e:
            print(f"调试操作出错: {e}")
            print(f"当前ZXTouch设备状态: {zx_device}")
            # 尝试重新连接
            print("尝试重新连接ZXTouch...")
            if connect_zxtouch():
                print("重新连接成功")
            else:
                print("重新连接失败")

# 主程序
if __name__ == "__main__":
    # 检查是否为调试模式
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        debug_mode()
        sys.exit(0)
    
    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 设置日志
    setup_logging()
    logging.info("iPhone智能门锁程序启动...")
    logging.info(f"休眠管理功能: {'启用' if ENABLE_SLEEP_MANAGEMENT else '禁用'}")
    logging.info(f"工作时间段: {START_CHECK_STATUS_HOUR}:00 - {STOP_CHECK_STATUS_HOUR}:00")
    logging.info("已启用Dim模式双颜色集匹配功能")
    
    # 启动定时任务
    schedule_tasks()

    if not initialize_system():
        logging.error("初始化失败，程序退出")
        exit(1)

    # MQTT
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        # MQTT连接
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)        
        # 启动MQTT客户端循环
        mqtt_client.loop_start()
        
        logging.info("系统启动完成，开始监听MQTT消息...")
        
        # 运行定时任务
        while True:
            # 运行待执行的任务并获取下一个任务的等待时间
            wait_time = run_pending_and_get_next_run()
            
            if wait_time is None or wait_time <= 0:
                # 没有待执行任务或任务已过期，短暂休眠后重新检查
                time.sleep(60)  # 1分钟后重新检查
            else:
                # 精确等待到下次任务执行时间
                time.sleep(wait_time)
    except Exception as e:
        logging.error(f"运行时错误: {e}")
        # 确保程序异常退出时也关闭Dim模式
        logging.info("程序异常退出，正在关闭Dim模式...")
        disable_dim_mode()
        exit(1)

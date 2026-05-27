#!/usr/bin/env python3

import os
import time

from zxtouch.client import zxtouch

IPHONE_IP = os.environ.get("IPHONE_IP", "YOUR_IPHONE_IP")

# 定义触摸类型常量
try:
    from zxtouch.touchtypes import *
    print("✅ 成功导入 zxtouch.touchtypes 常量")
except ImportError as e:
    print(f"⚠️  导入 touchtypes 失败: {e}")
    print("使用数字常量作为备选方案")
    # 根据之前测试，定义备选常量
    TOUCH_DOWN = 0
    TOUCH_UP = 2  
    TOUCH_MOVE = 1

def test_correct_zxtouch_api():
    """根据官方文档测试正确的ZXTouch API用法"""
    
    print("\n=== 正确的ZXTouch API测试 ===")
    print("根据官方GitHub文档的正确用法")
    print("测试坐标: (466, 125) - 相册图标")
    print("关键改进:")
    print("1. 使用 TOUCH_DOWN 和 TOUCH_UP 常量")
    print("2. 手指索引使用1-19范围（而不是0）")
    print("3. 完整的按下-抬起序列")
    print()
    
    # 连接设备
    try:
        device = zxtouch(IPHONE_IP)
        print(f"✅ 连接成功")
        screen_size = device.get_screen_size()
        print(f"📱 屏幕尺寸: {screen_size}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    # 相册坐标
    app_x, app_y = 466, 125
    
    # 显示当前常量值
    print(f"当前常量值: TOUCH_DOWN={TOUCH_DOWN}, TOUCH_UP={TOUCH_UP}")
    print()
    
    # 测试不同的正确方法
    test_methods = [
        # 方法1: 标准官方方法，手指索引1
        {
            "name": "方法1: 标准方法 (finger=1, 100ms延迟)",
            "code": lambda: test_touch_sequence(device, app_x, app_y, 1, 0.1)
        },
        
        # 方法2: 手指索引5（官方示例用的）
        {
            "name": "方法2: 官方示例 (finger=5, 100ms延迟)",
            "code": lambda: test_touch_sequence(device, app_x, app_y, 5, 0.1)
        },
        
        # 方法3: 更短延迟
        {
            "name": "方法3: 短延迟 (finger=1, 50ms延迟)",
            "code": lambda: test_touch_sequence(device, app_x, app_y, 1, 0.05)
        },
        
        # 方法4: 更长延迟
        {
            "name": "方法4: 长延迟 (finger=1, 200ms延迟)",
            "code": lambda: test_touch_sequence(device, app_x, app_y, 1, 0.2)
        },
        
        # 方法5: 尝试我们之前发现的type=0方法
        {
            "name": "方法5: 之前成功的单次type=0",
            "code": lambda: test_simple_touch(device, app_x, app_y)
        },
        
        # 方法6: 使用touch_with_list的正确格式
        {
            "name": "方法6: touch_with_list方法",
            "code": lambda: test_touch_with_list(device, app_x, app_y)
        }
    ]
    
    print("开始测试正确的ZXTouch API方法...")
    print("每次测试后请检查相册是否真正打开！\n")
    
    successful_methods = []
    
    for i, method in enumerate(test_methods, 1):
        print(f"🧪 测试 {i}/6: {method['name']}")
        
        try:
            method['code']()
            time.sleep(1)  # 等待应用反应
            
            # 检查是否成功
            response = input("   ❓ 相册应用打开了吗? (y/n): ").strip().lower()
            if response == 'y':
                successful_methods.append(method['name'])
                print("   🎉 成功！找到正确方法！")
                input("   📱 请关闭相册后按回车继续...")
            else:
                print("   ❌ 未打开")
                
        except Exception as e:
            print(f"   ❌ 执行失败: {e}")
        
        print()
        time.sleep(1)
    
    # 总结结果
    print("=" * 60)
    print("📊 测试总结:")
    if successful_methods:
        print("🎉 成功的方法:")
        for i, method in enumerate(successful_methods, 1):
            print(f"   {i}. {method}")
        print("\n💡 现在我们可以用正确的方法更新代码了！")
        return successful_methods[0] if successful_methods else None
    else:
        print("😞 仍然没有方法成功")
        print("🔍 可能的其他问题:")
        print("   - ZXTouch服务权限设置")
        print("   - iOS辅助功能设置")
        print("   - 需要特定的安全设置")
        return None

def test_touch_sequence(device, x, y, finger_index, delay):
    """测试标准的按下-延迟-抬起序列"""
    print(f"   按下 TOUCH_DOWN (finger={finger_index})...")
    device.touch(TOUCH_DOWN, finger_index, x, y)
    
    print(f"   等待 {delay}s...")
    time.sleep(delay)
    
    print(f"   抬起 TOUCH_UP (finger={finger_index})...")
    device.touch(TOUCH_UP, finger_index, x, y)
    
    print("   序列完成")

def test_simple_touch(device, x, y):
    """测试之前发现成功的简单type=0方法"""
    print("   使用之前成功的type=0方法...")
    device.touch(0, 0, x, y)
    print("   完成")

def test_touch_with_list(device, x, y):
    """测试touch_with_list方法"""
    print("   使用touch_with_list按下...")
    device.touch_with_list([
        {"type": TOUCH_DOWN, "finger_index": 1, "x": x, "y": y}
    ])
    
    time.sleep(0.1)
    
    print("   使用touch_with_list抬起...")
    device.touch_with_list([
        {"type": TOUCH_UP, "finger_index": 1, "x": x, "y": y}
    ])
    
    print("   完成")

def quick_verify():
    """快速验证导入是否正确"""
    print("=== 快速验证导入和常量 ===")
    
    try:
        device = zxtouch(IPHONE_IP)
        print("✅ 设备连接成功")
        print(f"✅ 常量可用 - TOUCH_DOWN={TOUCH_DOWN}, TOUCH_UP={TOUCH_UP}")
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 快速验证导入和常量")
    print("2. 完整的正确API测试")
    
    choice = input("请选择 (1/2): ").strip()
    
    if choice == "1":
        quick_verify()
    elif choice == "2":
        if quick_verify():
            print("\n" + "="*40)
            result = test_correct_zxtouch_api()
            if result:
                print(f"\n🏆 推荐使用方法: {result}")
        else:
            print("验证失败，无法进行完整测试")
    else:
        print("无效选择")

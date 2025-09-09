#!/usr/bin/env python3
"""
测试多帧图像上传功能

该脚本用于测试InstantSplat API的多帧图像上传功能，
验证动态n_views参数设置是否正常工作。
"""

import requests
import time
import json
from pathlib import Path

# API配置
API_BASE_URL = "http://localhost:3080"
TEST_IMAGE_DIR = Path("/home/livablecity/InstantSplat/Test_data/Image")

def upload_images_as_zip():
    """将多张图像打包成zip文件并上传"""
    import zipfile
    import os
    
    try:
        # 获取所有图像文件
        image_files = sorted(list(TEST_IMAGE_DIR.glob("*.jpg")) + list(TEST_IMAGE_DIR.glob("*.png")))
        print(f"找到 {len(image_files)} 张图像文件")
        
        # 选择前12张图像（如果有的话）
        selected_files = image_files[:12]
        
        if len(selected_files) < 3:
            print(f"错误：图像数量不足，找到{len(selected_files)}张，至少需要3张")
            return None
        
        print(f"选择了{len(selected_files)}张图像进行打包上传")
        
        # 创建临时zip文件
        zip_filename = "test_images.zip"
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, image_file in enumerate(selected_files):
                # 使用标准命名格式添加到zip中
                file_ext = image_file.suffix
                zip_name = f"image_{i:03d}{file_ext}"
                zipf.write(image_file, zip_name)
                print(f"  添加图像: {image_file.name} -> {zip_name}")
        
        print(f"\n创建zip文件成功: {zip_filename}")
        
        # 上传zip文件
        print("\n开始上传zip文件...")
        with open(zip_filename, 'rb') as f:
            files = {'file': (zip_filename, f, 'application/zip')}
            response = requests.post(f"{API_BASE_URL}/upload", files=files, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            task_id = data.get('task_id')
            print(f"zip文件上传成功，任务ID: {task_id}")
            return task_id
        else:
            print(f"zip文件上传失败: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"创建或上传zip文件失败: {e}")
        return None
    finally:
        # 清理临时zip文件
        if 'zip_filename' in locals() and os.path.exists(zip_filename):
            os.remove(zip_filename)
            print(f"清理临时文件: {zip_filename}")

def upload_single_image():
    """上传单张图像测试"""
    image_files = sorted(list(TEST_IMAGE_DIR.glob("*.jpg")) + list(TEST_IMAGE_DIR.glob("*.png")))
    if not image_files:
        print("未找到测试图像文件")
        return None
    
    test_image = image_files[0]
    print(f"上传单张图像: {test_image.name}")
    
    with open(test_image, 'rb') as f:
        files = {'file': (test_image.name, f, 'image/jpeg')}
        response = requests.post(f"{API_BASE_URL}/upload", files=files)
    
    return response

def check_task_status(task_id):
    """检查任务状态"""
    response = requests.get(f"{API_BASE_URL}/status/{task_id}")
    return response

def monitor_task(task_id, max_wait_time=300):
    """监控任务进度"""
    print(f"\n监控任务 {task_id} 的进度...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = check_task_status(task_id)
            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                progress = data.get('progress', 0)
                current_step = data.get('current_step', '')
                message = data.get('message', '')
                
                print(f"状态: {status}, 进度: {progress:.1f}%, 步骤: {current_step}, 消息: {message}")
                
                if status in ['completed', 'failed']:
                    return data
                    
            time.sleep(5)
        except Exception as e:
            print(f"检查状态时出错: {e}")
            time.sleep(5)
    
    print(f"任务监控超时 ({max_wait_time}秒)")
    return None

def main():
    """主测试函数"""
    print("=== InstantSplat 多帧图像上传测试 ===")
    
    # 检查API服务状态
    try:
        response = requests.get(f"{API_BASE_URL}/")
        if response.status_code != 200:
            print(f"API服务不可用: {response.status_code}")
            return
        print("API服务正常运行")
    except Exception as e:
        print(f"无法连接到API服务: {e}")
        return
    
    # 测试: 上传多张图像（zip文件）
    print("\n=== 测试: 上传多张图像（zip文件）===")
    task_id = upload_images_as_zip()
    if task_id:
        print(f"上传成功，任务ID: {task_id}")
        
        # 监控任务的进度
        print(f"监控任务: {task_id}")
        result = monitor_task(task_id)
        if result:
            print(f"任务完成，最终状态: {result.get('status')}")
            if result.get('status') == 'completed':
                print(f"处理时间: {result.get('processing_time', 'N/A')}秒")
                print(f"输出目录: {result.get('result_path', 'N/A')}")
                
                # 检查n_views参数是否正确设置
                print("\n检查输出目录结构...")
                import os
                output_base = "/home/livablecity/InstantSplat/output_infer/api_uploads"
                task_output_dir = Path(output_base) / task_id
                if task_output_dir.exists():
                    subdirs = [d for d in task_output_dir.iterdir() if d.is_dir()]
                    for subdir in subdirs:
                        if "_views" in subdir.name:
                            n_views_used = subdir.name.split("_")[0]
                            print(f"使用的n_views参数: {n_views_used}")
                            break
    else:
        print("上传失败: 没有成功的任务")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLY文件压缩测试脚本
测试splat-transform工具对指定PLY文件的压缩功能
"""

import os
import subprocess
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_ply_compression():
    """测试PLY文件压缩功能"""
    
    # 目标PLY文件路径
    ply_file_path = "/home/livablecity/InstantSplat/output_infer/api_uploads/cfb22392-9293-4c55-ac95-fd0300ed5d2b/8_views/point_cloud/iteration_500/point_cloud.ply"
    
    # 检查文件是否存在
    if not os.path.exists(ply_file_path):
        logger.error(f"PLY文件不存在: {ply_file_path}")
        return False
    
    # 获取原文件大小
    original_size = os.path.getsize(ply_file_path)
    logger.info(f"原文件大小: {original_size / (1024*1024):.2f} MB")
    
    # 生成压缩文件路径
    compressed_ply_path = ply_file_path.replace('.ply', '.compressed.ply')
    
    # 构建压缩命令（参考api_server.py中的逻辑）
    compress_command = [
        "/opt/glibc-2.38/lib/ld-linux-x86-64.so.2",
        "--library-path", "/opt/glibc-2.38/lib:/usr/lib/x86_64-linux-gnu",
        "/home/livablecity/.nvm/versions/node/v22.17.1/bin/node",
        "/home/livablecity/.nvm/versions/node/v22.17.1/bin/splat-transform",
        ply_file_path,
        compressed_ply_path
    ]
    
    logger.info(f"开始压缩PLY文件...")
    logger.info(f"输入文件: {ply_file_path}")
    logger.info(f"输出文件: {compressed_ply_path}")
    logger.info(f"压缩命令: {' '.join(compress_command)}")
    
    try:
        # 执行压缩命令
        result = subprocess.run(
            compress_command, 
            capture_output=True, 
            text=True, 
            timeout=300
        )
        
        # 输出命令执行结果
        logger.info(f"命令返回码: {result.returncode}")
        
        if result.stdout:
            logger.info(f"标准输出:\n{result.stdout}")
        
        if result.stderr:
            logger.info(f"标准错误:\n{result.stderr}")
        
        # 检查压缩是否成功
        if result.returncode == 0 and os.path.exists(compressed_ply_path):
            compressed_size = os.path.getsize(compressed_ply_path)
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            logger.info(f"✅ 压缩成功!")
            logger.info(f"压缩文件大小: {compressed_size / (1024*1024):.2f} MB")
            logger.info(f"压缩率: {compression_ratio:.2f}%")
            logger.info(f"压缩文件路径: {compressed_ply_path}")
            
            return True
        else:
            logger.error(f"❌ 压缩失败")
            logger.error(f"返回码: {result.returncode}")
            if result.stderr:
                logger.error(f"错误信息: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ 压缩超时（300秒）")
        return False
    except Exception as e:
        logger.error(f"❌ 压缩异常: {str(e)}")
        return False

def check_dependencies():
    """检查依赖工具是否存在"""
    logger.info("检查依赖工具...")
    
    # 检查glibc
    glibc_path = "/opt/glibc-2.38/lib/ld-linux-x86-64.so.2"
    if os.path.exists(glibc_path):
        logger.info(f"✅ glibc-2.38 存在: {glibc_path}")
    else:
        logger.error(f"❌ glibc-2.38 不存在: {glibc_path}")
        return False
    
    # 检查node
    node_path = "/home/livablecity/.nvm/versions/node/v22.17.1/bin/node"
    if os.path.exists(node_path):
        logger.info(f"✅ Node.js 存在: {node_path}")
    else:
        logger.error(f"❌ Node.js 不存在: {node_path}")
        return False
    
    # 检查splat-transform
    splat_path = "/home/livablecity/.nvm/versions/node/v22.17.1/bin/splat-transform"
    if os.path.exists(splat_path):
        logger.info(f"✅ splat-transform 存在: {splat_path}")
    else:
        logger.error(f"❌ splat-transform 不存在: {splat_path}")
        return False
    
    return True

if __name__ == "__main__":
    logger.info("=== PLY文件压缩测试开始 ===")
    
    # 检查依赖
    if not check_dependencies():
        logger.error("依赖检查失败，退出测试")
        exit(1)
    
    # 执行压缩测试
    success = test_ply_compression()
    
    if success:
        logger.info("=== 测试完成：压缩成功 ===")
        exit(0)
    else:
        logger.error("=== 测试完成：压缩失败 ===")
        exit(1)
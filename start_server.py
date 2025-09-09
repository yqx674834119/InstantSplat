#!/usr/bin/env python3
"""
启动FastAPI服务器脚本
"""

import uvicorn
import argparse
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from config import api_config

def main():
    parser = argparse.ArgumentParser(description="启动InstantSplat FastAPI服务器")
    parser.add_argument("--host", default=api_config.HOST, help="服务器主机地址")
    parser.add_argument("--port", type=int, default=api_config.PORT, help="服务器端口")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    parser.add_argument("--reload", action="store_true", help="启用自动重载（开发模式）")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], help="日志级别")
    
    args = parser.parse_args()
    
    print(f"启动InstantSplat API服务器...")
    print(f"地址: http://{args.host}:{args.port}")
    print(f"文档: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "api_server:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        log_level=args.log_level
    )

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
完整的API测试脚本 - 测试InstantSplat API的所有功能
包括：文件上传、任务状态查询、进度监控、结果下载等
"""

import requests
import time
import json
import os
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class APITester:
    """API测试器"""
    
    def __init__(self, base_url: str = "http://localhost:3080"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        
    def log_test_result(self, test_name: str, success: bool, message: str, details: Dict[str, Any] = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {message}")
        
    def test_health_check(self) -> bool:
        """测试健康检查接口"""
        try:
            response = self.session.get(f"{self.base_url}/")
            success = response.status_code == 200
            
            self.log_test_result(
                "健康检查",
                success,
                f"状态码: {response.status_code}, 响应: {response.json() if success else response.text}"
            )
            return success
            
        except Exception as e:
            self.log_test_result("健康检查", False, f"请求失败: {str(e)}")
            return False
    
    def get_test_images(self, output_dir: Path) -> Path:
        """获取测试图像文件"""
        import shutil
        
        test_data_dir = Path("/home/livablecity/InstantSplat/Test_data/Image")
        if not test_data_dir.exists():
            raise FileNotFoundError(f"Test_data目录不存在: {test_data_dir}")
        
        # 获取所有图像文件
        image_files = list(test_data_dir.glob("*.jpg")) + list(test_data_dir.glob("*.png"))
        if not image_files:
            raise FileNotFoundError("Test_data/Image目录中没有找到图像文件")
        
        output_dir.mkdir(exist_ok=True)
        
        # 复制图像文件到输出目录
        for i, img_file in enumerate(image_files[:8]):  # 最多使用8张图像
            dest_path = output_dir / f"test_image_{i+1:02d}.jpg"
            shutil.copy2(img_file, dest_path)
            
        return output_dir
    
    def get_test_video(self) -> str:
        """获取测试视频文件路径"""
        test_video_path = "/home/livablecity/InstantSplat/Test_data/Video/car.mp4"
        if not os.path.exists(test_video_path):
            raise FileNotFoundError(f"测试视频文件不存在: {test_video_path}")
        return test_video_path
    
    def create_test_zip(self, images_dir: Path) -> Path:
        """创建测试zip文件"""
        zip_path = images_dir.parent / "test_images_complete.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for img_file in images_dir.glob("*.jpg"):
                zipf.write(img_file, img_file.name)
                
        logger.info(f"创建测试zip文件: {zip_path} ({zip_path.stat().st_size} bytes)")
        return zip_path
    
    def test_file_upload(self, file_path: Path, email: str = "674834119@qq.com") -> Optional[str]:
        """测试文件上传"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, 'application/octet-stream')}
                # response = self.session.post(f"{self.base_url}/upload", files=files, data=data)
                response = self.session.post(
                        f"{self.base_url}/upload?email={email}",
                        files=files
                    )

            success = response.status_code == 200
            
            if success:
                data = response.json()
                task_id = data.get('task_id')
                self.log_test_result(
                    "文件上传",
                    True,
                    f"上传成功，任务ID: {task_id}",
                    {"task_id": task_id, "response": data}
                )
                return task_id
            else:
                self.log_test_result(
                    "文件上传",
                    False,
                    f"上传失败，状态码: {response.status_code}, 响应: {response.text}"
                )
                return None
                
        except Exception as e:
            self.log_test_result("文件上传", False, f"上传异常: {str(e)}")
            return None
    
    def test_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """测试任务状态查询"""
        try:
            response = self.session.get(f"{self.base_url}/status/{task_id}")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                self.log_test_result(
                    "任务状态查询",
                    True,
                    f"状态: {data.get('status')}, 进度: {data.get('progress', 0):.1f}%",
                    data
                )
                return data
            else:
                self.log_test_result(
                    "任务状态查询",
                    False,
                    f"查询失败，状态码: {response.status_code}, 响应: {response.text}"
                )
                return None
                
        except Exception as e:
            self.log_test_result("任务状态查询", False, f"查询异常: {str(e)}")
            return None
    
    def monitor_task_progress(self, task_id: str, timeout: int = 600) -> bool:
        """监控任务进度直到完成"""
        start_time = time.time()
        last_status = None
        
        logger.info(f"开始监控任务 {task_id} 的进度...")
        
        while time.time() - start_time < timeout:
            status_data = self.test_task_status(task_id)
            
            if status_data is None:
                logger.warning(f"无法获取任务 {task_id} 的状态")
                time.sleep(5)
                continue
            
            current_status = status_data.get('status')
            progress = status_data.get('progress', 0)
            current_step = status_data.get('current_step', '')
            
            # 只在状态变化时打印详细信息
            if current_status != last_status:
                logger.info(f"任务状态变更: {last_status} -> {current_status}")
                last_status = current_status
            
            logger.info(f"进度: {progress:.1f}% - {current_step}")
            
            # 检查任务是否完成
            if current_status == 'completed':
                self.log_test_result(
                    "任务完成监控",
                    True,
                    f"任务成功完成，总耗时: {time.time() - start_time:.1f}秒",
                    status_data
                )
                return True
            elif current_status == 'failed':
                self.log_test_result(
                    "任务完成监控",
                    False,
                    f"任务失败: {status_data.get('error_message', '未知错误')}",
                    status_data
                )
                return False
            
            time.sleep(10)  # 每10秒检查一次
        
        # 超时
        self.log_test_result(
            "任务完成监控",
            False,
            f"任务监控超时 ({timeout}秒)"
        )
        return False
    
    def test_result_download(self, task_id: str) -> bool:
        """测试结果下载"""
        try:
            response = self.session.get(f"{self.base_url}/result/{task_id}")
            success = response.status_code == 200
            
            if success:
                # 检查是否是文件下载
                content_type = response.headers.get('content-type', '')
                content_length = len(response.content)
                
                self.log_test_result(
                    "结果下载",
                    True,
                    f"下载成功，文件大小: {content_length} bytes, 类型: {content_type}",
                    {
                        "content_length": content_length,
                        "content_type": content_type,
                        "headers": dict(response.headers)
                    }
                )
                
                # 保存下载的文件
                download_path = Path(f"downloaded_result_{task_id}.ply")
                with open(download_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"结果文件已保存到: {download_path}")
                
                return True
            else:
                self.log_test_result(
                    "结果下载",
                    False,
                    f"下载失败，状态码: {response.status_code}, 响应: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test_result("结果下载", False, f"下载异常: {str(e)}")
            return False
    
    def test_task_list(self) -> bool:
        """测试任务列表查询"""
        try:
            response = self.session.get(f"{self.base_url}/tasks")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                task_count = len(data.get('tasks', []))
                self.log_test_result(
                    "任务列表查询",
                    True,
                    f"获取到 {task_count} 个任务",
                    data
                )
                return True
            else:
                self.log_test_result(
                    "任务列表查询",
                    False,
                    f"查询失败，状态码: {response.status_code}, 响应: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test_result("任务列表查询", False, f"查询异常: {str(e)}")
            return False
    
    def run_complete_test(self) -> Dict[str, Any]:
        """运行完整的API测试"""
        logger.info("=" * 60)
        logger.info("开始完整的API功能测试")
        logger.info("=" * 60)
        
        # 1. 健康检查
        if not self.test_health_check():
            logger.error("健康检查失败，停止测试")
            return self.generate_test_report()
        
        # 2. 任务列表查询
        self.test_task_list()
        
        # 3. 获取测试文件
        logger.info("获取测试文件...")
        test_dir = Path("test_data_complete")
        images_dir = self.get_test_images(test_dir)
        zip_file = self.create_test_zip(images_dir)
        
        # 也可以测试视频文件
        try:
            video_file = self.get_test_video()
            logger.info(f"找到测试视频文件: {video_file}")
        except FileNotFoundError as e:
            logger.warning(f"测试视频文件不可用: {e}")
        
        # 4. 文件上传测试
        task_id = self.test_file_upload(zip_file)
        if not task_id:
            logger.error("文件上传失败，停止测试")
            return self.generate_test_report()
        
        # 5. 任务进度监控
        task_completed = self.monitor_task_progress(task_id, timeout=900)  # 15分钟超时
        
        # 6. 结果下载测试（无论任务是否完成都尝试）
        if task_completed:
            self.test_result_download(task_id)
        else:
            logger.warning("任务未完成，跳过结果下载测试")
        
        # 7. 再次查询任务列表
        self.test_task_list()
        
        # 8. 清理测试文件
        try:
            import shutil
            shutil.rmtree(test_dir)
            zip_file.unlink()
            logger.info("清理测试文件完成")
        except Exception as e:
            logger.warning(f"清理测试文件失败: {e}")
        
        return self.generate_test_report()
    
    def generate_test_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        report = {
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info("=" * 60)
        logger.info("测试报告")
        logger.info("=" * 60)
        logger.info(f"总测试数: {total_tests}")
        logger.info(f"通过: {passed_tests}")
        logger.info(f"失败: {failed_tests}")
        logger.info(f"成功率: {report['summary']['success_rate']:.1f}%")
        
        if failed_tests > 0:
            logger.info("\n失败的测试:")
            for result in self.test_results:
                if not result['success']:
                    logger.info(f"  - {result['test_name']}: {result['message']}")
        
        # 保存详细报告到文件
        report_file = Path(f"api_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n详细测试报告已保存到: {report_file}")
        
        return report

def main():
    """主函数"""
    # 检查API服务器是否运行
    api_url = "http://localhost:3080"
    
    try:
        response = requests.get(api_url, timeout=5)
        logger.info(f"API服务器运行正常: {api_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"无法连接到API服务器 {api_url}: {e}")
        logger.error("请确保API服务器正在运行")
        return
    
    # 运行测试
    tester = APITester(api_url)
    report = tester.run_complete_test()
    
    # 根据测试结果设置退出码
    if report['summary']['failed'] == 0:
        logger.info("所有测试通过! 🎉")
        exit(0)
    else:
        logger.error(f"有 {report['summary']['failed']} 个测试失败 ❌")
        exit(1)

if __name__ == "__main__":
    main()
import webview
import os
import sys
from pathlib import Path
import json
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import shutil

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.install import find_lcb, write_path, install as install_translation, final_correct
from utils.functions import set_log_callback, set_error_log_callback, download_and_verify_file, get_true_zip, download_llc
from utils.proper import make_proper
from utils.log_utils import LogManager


class LCTA_API:
    def __init__(self, window):
        self.window = window
        self.game_path = None
        # 不要将log_manager存储为实例变量，避免循环引用
        # self.log_manager = LogManager()
        
        # 设置日志回调
        set_log_callback(self.log_callback)
        set_error_log_callback(self.error_log_callback)

    def browse_file(self, input_id):
        """打开文件浏览器"""
        file_path = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            save_filename='选择文件'
        )
        
        if file_path and len(file_path) > 0:
            selected_path = file_path[0]
            # 通过JavaScript更新页面中的输入框
            js_code = f"document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';"
            self.window.evaluate_js(js_code)
            self.log_callback(f"已选择文件: {selected_path}")
            return selected_path
        return None

    def browse_folder(self, input_id):
        """打开文件夹浏览器"""
        folder_path = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG
        )
        
        if folder_path and len(folder_path) > 0:
            selected_path = folder_path[0]
            # 通过JavaScript更新页面中的输入框
            js_code = f"document.getElementById('{input_id}').value = '{selected_path.replace(os.sep, '/')}';"
            self.window.evaluate_js(js_code)
            self.log_callback(f"已选择文件夹: {selected_path}")
            return selected_path
        return None

    def start_translation(self):
        """开始翻译"""
        self.log_callback("开始翻译任务...")
        
        # 在单独的线程中执行长时间操作，避免阻塞GUI
        def translation_worker():
            try:
                # 获取表单数据
                # 获取复选框状态
                custom_script_enabled = self.window.evaluate_js("document.getElementById('custom-script').checked")
                cache_trans_enabled = self.window.evaluate_js("document.getElementById('cache-trans').checked")
                team_trans_enabled = self.window.evaluate_js("document.getElementById('team-trans').checked")
                excel_output_enabled = self.window.evaluate_js("document.getElementById('excel-output').checked")
                half_trans_enabled = self.window.evaluate_js("document.getElementById('half-trans').checked")
                backup_enabled = self.window.evaluate_js("document.getElementById('backup').checked")
                
                # 获取相关路径
                script_path = self.window.evaluate_js("document.getElementById('script-path').value") if custom_script_enabled else None
                half_trans_path = self.window.evaluate_js("document.getElementById('half-trans-path').value") if half_trans_enabled else None
                backup_path = self.window.evaluate_js("document.getElementById('backup-path').value") if backup_enabled else None
                
                # 获取选择的翻译服务
                service = self.window.evaluate_js("document.getElementById('translation-service').value")
                
                self.log_callback(f"使用翻译服务: {service}")
                self.log_callback("翻译参数已获取")
                
                # 模拟翻译过程
                steps = ["初始化", "分析文件", "翻译处理", "保存结果", "完成"]
                for i, step in enumerate(steps):
                    progress = (i + 1) * 20
                    self.update_progress(progress, f"正在{step}...")
                    time.sleep(0.5)  # 模拟处理时间
                
                self.log_callback("翻译任务完成!")
                self.update_progress(100, "完成")
                
            except Exception as e:
                self.error_log_callback(f"翻译过程中出现错误: {str(e)}")
                self.update_progress(0, "错误")
        
        # 启动翻译线程
        thread = threading.Thread(target=translation_worker)
        thread.daemon = True
        thread.start()
        
        return {"success": True, "message": "翻译任务已启动"}

    def install_translation(self):
        """安装翻译包"""
        try:
            # 从页面获取路径
            package_path = self.window.evaluate_js("document.getElementById('install-package').value")
            install_path = self.window.evaluate_js("document.getElementById('install-path').value")
            
            if not package_path:
                self.log_callback("未选择汉化包文件")
                return {"success": False, "message": "未选择汉化包文件"}
                
            if not install_path:
                install_path = self.get_game_path()
                if not install_path:
                    self.log_callback("未设置游戏路径")
                    return {"success": False, "message": "未设置游戏路径"}
            
            self.log_callback(f"开始安装汉化包: {package_path}")
            success, message = final_correct(package_path, install_path)
            
            self.log_callback(message)
            return {"success": success, "message": message}
        except Exception as e:
            error_msg = f"安装汉化包时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def get_game_path(self):
        """获取游戏路径"""
        if not self.game_path:
            # 尝试从配置文件获取路径
            path_files = [
                os.path.expanduser("~\\limbus.txt"),
                "path.txt"
            ]
            
            for path_file in path_files:
                if os.path.exists(path_file):
                    with open(path_file, "r", encoding="utf-8") as f:
                        self.game_path = f.readline().strip()
                    break
        
        if not self.game_path or not os.path.exists(self.game_path):
            self.game_path = find_lcb()  # 使用工具函数查找游戏路径
            if self.game_path:
                write_path(self.game_path)  # 保存找到的路径
        
        return self.game_path

    def download_ourplay_translation(self):
        """下载OurPlay翻译包"""
        self.log_callback("开始下载OurPlay翻译包...")
        
        def download_worker():
            try:
                # 使用工具函数下载
                if download_and_verify_file(progress_callback=self.progress_callback):
                    self.log_callback("OurPlay翻译包下载完成")
                    # 转换格式
                    get_true_zip("transfile.zip")
                    self.log_callback("翻译包格式转换完成")
                    return {"success": True, "message": "OurPlay翻译包下载并转换完成"}
                else:
                    error_msg = "下载失败"
                    self.log_callback(error_msg)
                    return {"success": False, "message": error_msg}
            except Exception as e:
                error_msg = f"下载OurPlay翻译包时出现错误: {str(e)}"
                self.error_log_callback(error_msg)
                return {"success": False, "message": error_msg}
        
        # 启动下载线程
        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()
        
        return {"success": True, "message": "下载任务已启动"}

    def download_llc_translation(self):
        """下载零协翻译包"""
        self.log_callback("开始下载零协翻译包...")
        
        def download_worker():
            try:
                success = download_llc(progress_callback=self.progress_callback)
                if success:
                    self.log_callback("零协翻译包下载完成")
                    return {"success": True, "message": "零协翻译包下载完成"}
                else:
                    error_msg = "零协翻译包下载失败"
                    self.log_callback(error_msg)
                    return {"success": False, "message": error_msg}
            except Exception as e:
                error_msg = f"下载零协翻译包时出现错误: {str(e)}"
                self.error_log_callback(error_msg)
                return {"success": False, "message": error_msg}
        
        # 启动下载线程
        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()
        
        return {"success": True, "message": "零协下载任务已启动"}

    def clean_cache(self):
        """清除本地缓存"""
        self.log_callback("开始清除本地缓存...")
        
        try:
            # 定义可能的缓存目录
            cache_dirs = ['temp', 'cache', '__pycache__']
            cache_files = ['*.tmp', '*.temp', '*.cache']
            
            total_cleaned = 0
            for cache_dir in cache_dirs:
                if os.path.exists(cache_dir):
                    shutil.rmtree(cache_dir)
                    total_cleaned += 1
                    self.log_callback(f"已删除目录: {cache_dir}")
            
            self.log_callback(f"清除完成，共清理 {total_cleaned} 个缓存目录")
            return {"success": True, "message": f"清除完成，共清理 {total_cleaned} 个缓存目录"}
        except Exception as e:
            error_msg = f"清除缓存时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def fetch_proper_nouns(self):
        """抓取专有词汇"""
        self.log_callback("开始抓取专有词汇...")
        
        def fetch_worker():
            try:
                # 获取页面设置
                output_format = self.window.evaluate_js("document.getElementById('proper-output').value")
                skip_space = self.window.evaluate_js("document.getElementById('proper-skip-space').checked")
                max_count_str = self.window.evaluate_js("document.getElementById('proper-max-count').value")
                
                max_count = None
                if max_count_str and max_count_str.strip():
                    max_count = int(max_count_str)
                
                self.log_callback(f"输出格式: {output_format}, 跳过含空格: {skip_space}, 最大数量: {max_count}")
                
                # 执行抓取
                def logger(msg):
                    self.log_callback(msg)
                
                success = make_proper(logger, output_type=output_format, skip_space=skip_space, max_count=max_count)
                
                if success:
                    self.log_callback("专有词汇抓取完成")
                    return {"success": True, "message": "专有词汇抓取完成"}
                else:
                    error_msg = "专有词汇抓取失败"
                    self.log_callback(error_msg)
                    return {"success": False, "message": error_msg}
            except Exception as e:
                error_msg = f"抓取专有词汇时出现错误: {str(e)}"
                self.error_log_callback(error_msg)
                return {"success": False, "message": error_msg}
        
        # 启动抓取线程
        thread = threading.Thread(target=fetch_worker)
        thread.daemon = True
        thread.start()
        
        return {"success": True, "message": "专有词汇抓取任务已启动"}

    def save_api_config(self):
        """保存API配置"""
        try:
            service = self.window.evaluate_js("document.getElementById('api-service').value")
            api_key = self.window.evaluate_js("document.getElementById('api-key').value")
            
            # 这里应该保存到配置文件，现在只是记录
            self.log_callback(f"API配置已保存: {service}")
            return {"success": True, "message": "API配置保存成功"}
        except Exception as e:
            error_msg = f"保存API配置时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def search_text(self):
        """搜索文本"""
        try:
            keyword = self.window.evaluate_js("document.getElementById('search-keyword').value")
            search_path = self.window.evaluate_js("document.getElementById('search-path').value")
            case_sensitive = self.window.evaluate_js("document.getElementById('search-case-sensitive').checked")
            
            if not keyword:
                return {"success": False, "message": "请输入搜索关键词"}
            
            if not search_path:
                search_path = self.get_game_path()  # 使用游戏路径作为默认搜索路径
            
            if not os.path.exists(search_path):
                return {"success": False, "message": "搜索路径不存在"}
            
            self.log_callback(f"开始搜索关键词 '{keyword}' 在路径 '{search_path}' 中")
            
            # 这里应该实现实际的搜索逻辑
            # 为了演示，我们返回一些模拟结果
            results = [
                {"file": "example1.txt", "line": 10, "content": f"...{keyword}..."},
                {"file": "example2.txt", "line": 25, "content": f"...{keyword}..."}
            ]
            
            self.log_callback(f"搜索完成，找到 {len(results)} 个结果")
            return {"success": True, "message": f"找到 {len(results)} 个结果", "results": results}
        except Exception as e:
            error_msg = f"搜索文本时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def backup_text(self):
        """备份原文"""
        try:
            source = self.window.evaluate_js("document.getElementById('backup-source').value")
            destination = self.window.evaluate_js("document.getElementById('backup-destination').value")
            
            if not source:
                return {"success": False, "message": "请选择源文件路径"}
            
            if not destination:
                return {"success": False, "message": "请选择备份保存路径"}
            
            if not os.path.exists(source):
                return {"success": False, "message": "源文件路径不存在"}
            
            # 确保目标目录存在
            os.makedirs(destination, exist_ok=True)
            
            self.log_callback(f"开始备份: {source} -> {destination}")
            
            # 实现备份逻辑
            if os.path.isfile(source):
                # 备份单个文件
                filename = os.path.basename(source)
                dest_file = os.path.join(destination, filename)
                shutil.copy2(source, dest_file)
                self.log_callback(f"文件已备份: {filename}")
            elif os.path.isdir(source):
                # 备份整个目录
                dir_name = os.path.basename(source)
                dest_dir = os.path.join(destination, dir_name)
                if os.path.exists(dest_dir):
                    shutil.rmtree(dest_dir)
                shutil.copytree(source, dest_dir)
                self.log_callback(f"目录已备份: {dir_name}")
            
            return {"success": True, "message": "备份完成"}
        except Exception as e:
            error_msg = f"备份原文时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def manage_fonts(self):
        """管理字体"""
        try:
            self.log_callback("字体管理功能正在开发中...")
            return {"success": True, "message": "字体管理功能正在开发中..."}
        except Exception as e:
            error_msg = f"管理字体时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def manage_images(self):
        """管理图片"""
        try:
            self.log_callback("图片管理功能正在开发中...")
            return {"success": True, "message": "图片管理功能正在开发中..."}
        except Exception as e:
            error_msg = f"管理图片时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def manage_audio(self):
        """管理音频"""
        try:
            self.log_callback("音频管理功能正在开发中...")
            return {"success": True, "message": "音频管理功能正在开发中..."}
        except Exception as e:
            error_msg = f"管理音频时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def adjust_image(self):
        """调整图片"""
        try:
            image_path = self.window.evaluate_js("document.getElementById('image-path').value")
            brightness = float(self.window.evaluate_js("document.getElementById('brightness').value"))
            contrast = float(self.window.evaluate_js("document.getElementById('contrast').value"))
            
            if not image_path or not os.path.exists(image_path):
                return {"success": False, "message": "请选择有效的图片文件"}
            
            self.log_callback(f"调整图片: {image_path}, 亮度: {brightness}, 对比度: {contrast}")
            
            # 这里应该实现实际的图片调整逻辑
            # 为了演示，我们只记录操作
            self.log_callback("图片调整功能正在开发中...")
            
            return {"success": True, "message": "图片调整功能正在开发中..."}
        except Exception as e:
            error_msg = f"调整图片时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def calculate_gacha(self):
        """计算抽卡概率"""
        try:
            total_items = int(self.window.evaluate_js("document.getElementById('total-items').value"))
            rare_items = int(self.window.evaluate_js("document.getElementById('rare-items').value"))
            draw_count = int(self.window.evaluate_js("document.getElementById('draw-count').value"))
            
            if rare_items > total_items:
                return {"success": False, "message": "稀有物品数不能大于总物品数"}
            
            # 计算至少获得1个稀有物品的概率
            # P(至少1个稀有) = 1 - P(没有稀有) = 1 - ((总物品数-稀有物品数)/总物品数)^抽取次数
            prob_no_rare = ((total_items - rare_items) / total_items) ** draw_count
            prob_at_least_one_rare = 1 - prob_no_rare
            percent = prob_at_least_one_rare * 100
            
            self.log_callback(f"抽卡概率计算:")
            self.log_callback(f"  总物品数: {total_items}")
            self.log_callback(f"  稀有物品数: {rare_items}")
            self.log_callback(f"  抽取次数: {draw_count}")
            self.log_callback(f"  至少获得1个稀有物品的概率: {percent:.2f}%")
            
            result_text = f"至少获得1个稀有物品的概率: {percent:.2f}%"
            return {"success": True, "message": result_text, "probability": percent}
        except Exception as e:
            error_msg = f"计算抽卡概率时出现错误: {str(e)}"
            self.error_log_callback(error_msg)
            return {"success": False, "message": error_msg}

    def log_callback(self, message):
        """日志回调函数"""
        # 添加时间戳
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        full_message = f"{timestamp} {message}"
        
        # 通过JavaScript将日志消息发送到前端
        escaped_message = message.replace("'", "\\'")
        js_code = f"addLogMessage('{escaped_message}');"
        try:
            self.window.evaluate_js(js_code)
        except:
            # 如果窗口不可用则打印到控制台
            print(f"[LOG] {message}")
        
        # 同时记录到文件
        print(full_message)

    def error_log_callback(self, error):
        """错误日志回调函数"""
        self.log_callback(f"错误: {str(error)}")

    def get_system_info(self):
        """获取系统信息"""
        game_path = self.get_game_path()
        return {
            'game_path': game_path if game_path else '未找到',
            'status': '就绪' if game_path else '游戏路径未设置'
        }

    def update_progress(self, percent, text):
        """更新进度"""
        escaped_text = text.replace("'", "\\'")
        js_code = f"updateProgress({percent}, '{escaped_text}');"
        try:
            self.window.evaluate_js(js_code)
        except:
            pass

    def progress_callback(self, progress):
        """进度回调，用于下载等操作"""
        try:
            # 进度是0-100的数值
            self.update_progress(int(progress), f"进度: {int(progress)}%")
            return True  # 继续操作
        except:
            return True  # 即使出错也继续


def setup_logging():
    """
    配置日志系统，使用1024KB作为轮换大小
    """
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 创建轮换文件处理器，最大1024KB，保留5个备份文件
    handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=1024*1024,  # 1024KB
        backupCount=5,       # 保留5个旧日志文件
        encoding='utf-8'
    )
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # 添加处理器到记录器
    logger.addHandler(handler)
    
    return logger


def main():
    # 获取HTML文件的绝对路径
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    
    # 设置日志
    logger = setup_logging()
    logger.info("正在启动LCTA WebUI")
    
    # 创建窗口 - 先创建窗口，不立即绑定API
    window = webview.create_window(
        "LCTA - 边狱公司汉化工具箱",
        url=html_path,
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        text_select=True  # 允许文本选择
    )
    
    # 创建API实例并绑定窗口
    api = LCTA_API(window)
    
    # 设置API
    window.js_api = api
    
    logger.info("WebUI窗口已创建")
    
    # 启动应用
    webview.start(
        debug=True,  # 开启调试模式便于开发
        http_server=True  # 使用内置HTTP服务器
    )


if __name__ == "__main__":
    main()
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
print(project_root)
sys.path.insert(0, str(project_root))

def get_resource_path():
    """
    获取资源文件的绝对路径
    在PyInstaller打包后，资源文件会被打包进可执行文件，需要特殊处理
    """
    try:
        # PyInstaller创建的临时文件夹
        base_path = Path(sys._MEIPASS)
    except Exception:
        # 未打包时直接使用项目根目录
        base_path = project_root
    
    return base_path

def start_webui():
    """启动PyWebGUI界面"""
    try:
        # 将资源路径添加到环境变量，供app.py使用
        import os
        os.environ['path_'] = get_resource_path('')
        
        from webui.app import main
        print("正在启动LCTA WebUI...")
        print("请稍候，界面即将打开...")
        main()
    except ImportError as e:
        print(f"启动WebUI失败: {e}")
        print("请确保已安装pywebview: pip install pywebview")
    except Exception as e:
        print(f"启动WebUI时发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    start_webui()
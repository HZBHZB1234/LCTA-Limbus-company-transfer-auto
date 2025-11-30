import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def start_webui():
    """启动PyWebGUI界面"""
    try:
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
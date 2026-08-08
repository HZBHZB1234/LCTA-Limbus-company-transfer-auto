import ctypes
import webbrowser
import webview
import sys

class customStdout:
    def __init__(self):
        self.original_stdout = sys.stdout
        sys.stdout = self
        self.messages = []

    def write(self, message):
        self.messages.append(message)
        self.original_stdout.write(message)
        self.original_stdout.flush()  # 确保消息立即输出

    def flush(self):
        self.original_stdout.flush()
    
    def reset(self):
        sys.stdout = self.original_stdout


def evalRuntime():
    try:
        from webutils.clr_bootstrap import ensure_clr
        ensure_clr()
        print('clr导入成功，使用netfx')
    except Exception as e:
        print(f'clr导入失败: {e}')
        return True
    return False

def evalHtml():
    out = customStdout()
    ctypes.windll.user32.MessageBoxW(0, '即将打开一个测试窗口，如正常打开，请关闭窗口。', '环境测试', 0x40)
    window = webview.create_window('LCTA 运行环境测试',
                                    'https://bing.com',)
    try:
        webview.start()
    except Exception as e:
        print(f'webview启动失败: {e}')
        import traceback
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(0, '未知原因', '环境测试错误', 0x10)
        return True
    out.reset()
    messages = ''.join(out.messages)
    if 'mshtml' in messages.lower():
        print('请下载webview2')
        webbrowser.open('https://go.microsoft.com/fwlink/p/?LinkId=2124703')
        return True

if __name__ == '__main__':
    if not evalRuntime():
        if not evalHtml():
            print('环境测试通过')
    input('回车键以退出...')
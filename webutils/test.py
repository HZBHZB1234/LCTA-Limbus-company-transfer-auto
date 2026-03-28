import webbrowser
import webview
import os
import sys
import tkinter as tk
from tkinter import messagebox

root = tk.Tk()
root.withdraw()

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
        try:
            import clr
            print('clr导入成功，使用netfx')
        except Exception as e:
            print(f'clr使用netfx导入失败: {e}')
            try:
                os.environ['PYTHONNET_RUNTIME']='coreclr'
                import clr
                print('clr导入成功，使用coreclr')
            except Exception as e:
                print(f'clr使用coreclr导入失败: {e}')
                os.environ['PYTHONNET_RUNTIME']='mono'
                import clr
                print('clr导入成功，使用mono')
    except:
        print('clr导入失败')
        webbrowser.open('https://download.mono-project.com/archive/6.12.0/windows-installer/mono-6.12.0.206-x64-0.msi')
        return True

def evalHtml():
    out = customStdout()
    messagebox.showinfo('环境测试', '即将打开一个测试窗口，如正常打开，请关闭窗口。')
    window = webview.create_window('LCTA 运行环境测试',
                                    'https://bing.com',)
    try:
        webview.start()
    except Exception as e:
        print(f'webview启动失败: {e}')
        import traceback
        traceback.print_exc()
        messagebox.showerror('环境测试错误', '未知原因')
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
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <direct.h>
#include <process.h>
#include <windows.h>

int main() {
    // 设置运行目录到应用所在目录
    char exe_path[MAX_PATH];
    GetModuleFileName(NULL, exe_path, MAX_PATH);
    char* last_slash = strrchr(exe_path, '\\');
    if (last_slash != NULL) {
        *last_slash = '\0';
        chdir(exe_path);
    }
    
    // 检测文件完整性
    // 检查必要的文件是否存在
    FILE *f = fopen("code\\start_webui.py", "r");
    if (f == NULL) {
        printf("Error: code\\start_webui.py not found!\n");
        MessageBox(NULL, "Error: code\\start_webui.py not found!", "Startup Error", MB_OK | MB_ICONERROR);
        return 1;
    }
    fclose(f);
    
    const char* python_paths[] = {
        ".\\code\\venv\\Scripts\\python.exe",  // 虚拟环境Python
    };
    
    int num_paths = sizeof(python_paths) / sizeof(python_paths[0]);
    char python_cmd[MAX_PATH];
    int python_found = 0;
    
    for (int i = 0; i < num_paths; i++) {
        f = fopen(python_paths[i], "r");
        if (f != NULL) {
            fclose(f);
            strcpy(python_cmd, python_paths[i]);
            python_found = 1;
            break;
        }
    }
    
    if (!python_found) {
        printf("Error: Python interpreter not found!\n");
        MessageBox(NULL, "Error: Python interpreter not found!", "Startup Error", MB_OK | MB_ICONERROR);
        return 1;
    }
    
    // 使用找到的Python解释器启动应用，隐藏控制台窗口
    char command[500];
    snprintf(command, sizeof(command), "%s code\\start_webui.py", python_cmd);
    
    // 使用CreateProcess替代system以隐藏控制台窗口
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE; // 隐藏窗口
    
    ZeroMemory(&pi, sizeof(pi));
    
    // 创建进程
    if (!CreateProcess(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        printf("Failed to create process!\n");
        MessageBox(NULL, "Failed to create process!", "Startup Error", MB_OK | MB_ICONERROR);
        return 1;
    }
    
    // 等待进程结束
    WaitForSingleObject(pi.hProcess, INFINITE);
    
    // 关闭进程和线程句柄
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    return 0;
}
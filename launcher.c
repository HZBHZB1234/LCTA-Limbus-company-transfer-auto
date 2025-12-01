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
    FILE *f = fopen("start_webui.py", "r");
    if (f == NULL) {
        printf("Error: start_webui.py not found!\n");
        MessageBox(NULL, "Error: start_webui.py not found!", "Startup Error", MB_OK | MB_ICONERROR);
        return 1;
    }
    fclose(f);
    
    // 检查Python解释器（优先使用系统Python，备选用虚拟环境）
    const char* python_paths[] = {
        "python.exe",                    // 系统Python
        ".\\venv\\Scripts\\python.exe",  // 虚拟环境Python
        "..\\venv\\Scripts\\python.exe"  // 上级目录的虚拟环境Python
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
    
    // 使用找到的Python解释器启动应用
    char command[500];
    snprintf(command, sizeof(command), "%s start_webui.py", python_cmd);
    
    // 执行命令
    int result = system(command);
    
    if (result != 0) {
        printf("Application exited with error code: %d\n", result);
    }
    
    return result;
}
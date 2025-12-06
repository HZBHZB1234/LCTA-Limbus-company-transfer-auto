#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <direct.h>
#include <shlwapi.h>

// 函数声明
int setup_environment();
int find_python_executable(char* python_path, size_t buffer_size);
int verify_python_environment(const char* python_path);
int run_python_script(const char* python_path, const char* script_path);
void show_error_message(const char* title, const char* message);

int main() {
    printf("Starting LCTA Launcher...\n");

    HWND console = GetConsoleWindow();
    ShowWindow(console, SW_HIDE);
    
    // 1. 设置工作目录到应用所在目录
    if (!setup_environment()) {
        return 1;
    }
    
    // 2. 查找Python可执行文件
    char python_path[MAX_PATH];
    if (!find_python_executable(python_path, sizeof(python_path))) {
        show_error_message("Python Not Found", 
            "Cannot find Python interpreter.\n\n"
            "Please ensure the application files are complete.\n"
            "Try re-downloading the application.");
        return 1;
    }
    
    printf("Python found at: %s\n", python_path);
    
    // 3. 验证Python环境
    if (!verify_python_environment(python_path)) {
        show_error_message("Python Environment Error",
            "Python environment verification failed.\n\n"
            "The embedded Python may be corrupted.\n"
            "Try re-downloading the application.");
        return 1;
    }
    
    // 4. 设置环境变量
    char exe_dir[MAX_PATH];
    GetModuleFileName(NULL, exe_dir, MAX_PATH);
    PathRemoveFileSpec(exe_dir);
    
    // 设置PYTHONPATH
    char pythonpath[MAX_PATH * 2];
    snprintf(pythonpath, sizeof(pythonpath), 
             "%s\\code\\venv\\Lib\\site-packages;%s\\code", 
             exe_dir, exe_dir);
    
    if (!SetEnvironmentVariable("PYTHONPATH", pythonpath)) {
        printf("Warning: Failed to set PYTHONPATH environment variable\n");
    }
    
    // 设置其他有用的环境变量
    SetEnvironmentVariable("PYTHONUNBUFFERED", "1");
    SetEnvironmentVariable("PYTHONIOENCODING", "utf-8");
    
    // 5. 构建脚本路径
    char script_path[MAX_PATH];
    snprintf(script_path, sizeof(script_path), 
             "%s\\code\\start_webui.py", exe_dir);
    
    // 6. 检查脚本是否存在
    if (GetFileAttributes(script_path) == INVALID_FILE_ATTRIBUTES) {
        char error_msg[512];
        snprintf(error_msg, sizeof(error_msg),
                 "Main script not found:\n%s\n\n"
                 "Please ensure all application files are present.",
                 script_path);
        show_error_message("File Missing", error_msg);
        return 1;
    }
    
    printf("Script path: %s\n", script_path);
    printf("PYTHONPATH: %s\n", pythonpath);
    
    // 7. 运行Python脚本
    printf("Launching application...\n");
    if (!run_python_script(python_path, script_path)) {
        show_error_message("Application Error",
            "Failed to start the application.\n\n"
            "Possible causes:\n"
            "1. Python script has errors\n"
            "2. Missing dependencies\n"
            "3. Permission issues\n\n"
            "Check the console output for details.");
        return 1;
    }
    
    return 0;
}

// 设置工作环境
int setup_environment() {
    char exe_path[MAX_PATH];
    
    // 获取当前可执行文件路径
    if (!GetModuleFileName(NULL, exe_path, MAX_PATH)) {
        show_error_message("System Error", "Cannot determine executable location.");
        return 0;
    }
    
    // 移除文件名部分，只保留目录
    PathRemoveFileSpec(exe_path);
    
    printf("Executable directory: %s\n", exe_path);
    
    // 切换到应用目录
    if (!SetCurrentDirectory(exe_path)) {
        char error_msg[256];
        snprintf(error_msg, sizeof(error_msg),
                 "Cannot change to application directory:\n%s", exe_path);
        show_error_message("Directory Error", error_msg);
        return 0;
    }
    
    return 1;
}

// 查找Python可执行文件
int find_python_executable(char* python_path, size_t buffer_size) {
    // 只检查一个路径就足够了
    const char* python_exe = ".\\code\\venv\\Bins\\python.exe";
    
    printf("Searching for Python interpreter...\n");
    printf("  Checking: %s\n", python_exe);
    
    if (GetFileAttributes(python_exe) != INVALID_FILE_ATTRIBUTES) {
        // 获取完整路径
        char full_path[MAX_PATH];
        if (GetFullPathName(python_exe, MAX_PATH, full_path, NULL)) {
            strncpy(python_path, full_path, buffer_size - 1);
            python_path[buffer_size - 1] = '\0';
            return 1;
        }
    }
    
    return 0;
}

// 验证Python环境
int verify_python_environment(const char* python_path) {
    printf("Verifying Python environment...\n");
    
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_SHOW;  // 修改为显示控制台窗口
    
    ZeroMemory(&pi, sizeof(pi));
    
    // 构建命令行 - 使用临时文件来捕获输出
    char command_line[1024];
    snprintf(command_line, sizeof(command_line),
             "\"%s\" -c \"import sys; print('Python', sys.version); import site; print('Site packages:', site.getsitepackages());\"",
             python_path);
    
    printf("Verification command line: %s\n", command_line);
    
    // 创建进程进行验证
    if (!CreateProcess(NULL,           // 不使用模块名
                       command_line,   // 命令行
                       NULL,           // 进程句柄不可继承
                       NULL,           // 线程句柄不可继承
                       FALSE,          // 不继承句柄
                       0,              // 移除CREATE_NO_WINDOW标志
                       NULL,           // 使用父进程环境
                       NULL,           // 使用父进程目录
                       &si,            // 启动信息
                       &pi)) {         // 进程信息
        printf("CreateProcess failed (%lu)\n", GetLastError());
        return 0;
    }
    
    // 等待进程结束
    WaitForSingleObject(pi.hProcess, 10000); // 等待最多10秒
    
    // 获取退出代码
    DWORD exit_code;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    
    // 关闭句柄
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    if (exit_code != 0) {
        printf("Python verification failed with code: %lu\n", exit_code);
        return 0;
    }
    
    return 1;
}

// 运行Python脚本
int run_python_script(const char* python_path, const char* script_path) {
    STARTUPINFO si;
    PROCESS_INFORMATION pi;
    
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_SHOW;  // 修改为显示控制台窗口
    
    ZeroMemory(&pi, sizeof(pi));
    
    // 构建命令行
    char command_line[1024];
    snprintf(command_line, sizeof(command_line),
             "\"%s\" \"%s\"",
             python_path, script_path);
    
    printf("Command line: %s\n", command_line);
    
    // 创建进程
    if (!CreateProcess(NULL,           // 不使用模块名
                       command_line,   // 命令行
                       NULL,           // 进程句柄不可继承
                       NULL,           // 线程句柄不可继承
                       FALSE,          // 不继承句柄
                       0,              // 移除CREATE_NO_WINDOW标志
                       NULL,           // 使用父进程环境
                       NULL,           // 使用父进程目录
                       &si,            // 启动信息
                       &pi)) {         // 进程信息
        printf("CreateProcess failed (%lu)\n", GetLastError());
        return 0;
    }
    
    printf("Application started (PID: %lu)\n", pi.dwProcessId);
    
    // 等待进程结束（可选）
    WaitForSingleObject(pi.hProcess, INFINITE);
    
    // 关闭句柄
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    
    return 1;
}

// 显示错误消息对话框
void show_error_message(const char* title, const char* message) {
    // 也在控制台输出错误
    printf("ERROR: %s\n", title);
    printf("%s\n", message);
    
    // 显示消息框
    MessageBox(NULL, message, title, MB_OK | MB_ICONERROR);
}
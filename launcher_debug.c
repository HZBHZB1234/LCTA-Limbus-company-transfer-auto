#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <direct.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <wincrypt.h>

// 函数声明
int setup_environment();
int find_python_executable(char* python_path, size_t buffer_size);
int verify_python_hash(const char* python_path);
int run_python_script(const char* python_path, const char* script_path);
void show_error_message(const char* title, const char* message);
void set_steam_argv(int argc, char* argv[], int launcher_index);
int calculate_file_hash(const char* file_path, char* hash_hex, size_t hex_size);
int verify_embedded_python();

#define EXPECTED_PYTHON_HASH "0fe699e2cb61a2cbe449a34eee56bd6175fbeb6ee7dc1261b0c338574c010d2b"

int main(int argc, char* argv[]) {
    printf("Starting LCTA Launcher...\n");
    
    // 检查命令行参数
    int show_console = 1;
    char script_name[MAX_PATH] = "code\\start_webui.py";
    
    int launcher_index = -1;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-launcher") == 0) {
            show_console = 1;  // 显示控制台窗口
            strcpy(script_name, "code\\launcher\\main.py");
            launcher_index = i; // 记录-launcher参数的位置
            printf("Launcher mode detected, starting launcher GUI...\n");
            break;
        }
    }
    
    // 根据参数决定是否隐藏控制台窗口
    HWND console = GetConsoleWindow();
    if (!show_console) {
        ShowWindow(console, SW_HIDE);
        printf("Console window hidden\n");
    } else {
        ShowWindow(console, SW_SHOW);
        printf("Console window shown\n");
    }
    
    // 如果是launcher模式，设置steam_argv环境变量
    if (launcher_index != -1) {
        set_steam_argv(argc, argv, launcher_index);
    }
    
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
    
    // 3. 通过哈希验证Python可执行文件
    if (!verify_python_hash(python_path)) {
        show_error_message("Python Integrity Error",
            "Python executable integrity verification failed.\n\n"
            "The embedded Python may be corrupted or modified.\n"
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
             "%s\\%s", exe_dir, script_name);
    
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

// 设置steam_argv环境变量，存储-launcher之后的所有参数
void set_steam_argv(int argc, char* argv[], int launcher_index) {
    if (launcher_index + 1 >= argc) {
        // 没有额外参数，设置为空环境变量
        SetEnvironmentVariable("steam_argv", "");
        printf("Set steam_argv to empty (no additional arguments)\n");
        return;
    }
    
    // 计算需要的缓冲区大小
    int total_len = 0;
    for (int i = launcher_index + 1; i < argc; i++) {
        total_len += strlen(argv[i]);
        if (i < argc - 1) {
            total_len += 1; // 为分隔符空格预留空间
        }
    }
    
    // 分配缓冲区
    char* steam_argv = malloc(total_len + 1);
    if (steam_argv == NULL) {
        printf("Failed to allocate memory for steam_argv\n");
        return;
    }
    
    // 组合参数
    steam_argv[0] = '\0'; // 初始化为空字符串
    for (int i = launcher_index + 1; i < argc; i++) {
        strcat(steam_argv, argv[i]);
        if (i < argc - 1) {
            strcat(steam_argv, " "); // 添加分隔符
        }
    }
    
    // 设置环境变量
    SetEnvironmentVariable("steam_argv", steam_argv);
    printf("Set steam_argv to: %s\n", steam_argv);
    
    // 释放内存
    free(steam_argv);
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

// 通过哈希验证Python可执行文件
int verify_python_hash(const char* python_path) {
    printf("Verifying Python executable integrity via SHA256 hash...\n");
    
    char calculated_hash[65]; // SHA256哈希是64个字符 + 空终止符
    if (!calculate_file_hash(python_path, calculated_hash, sizeof(calculated_hash))) {
        printf("Failed to calculate file hash\n");
        return 0;
    }
    
    printf("Calculated hash: %s\n", calculated_hash);
    printf("Expected hash: %s\n", EXPECTED_PYTHON_HASH);
    
    // 比较哈希值
    if (strcmp(calculated_hash, EXPECTED_PYTHON_HASH) != 0) {
        printf("Hash mismatch! File may be corrupted or modified.\n");
        return 0;
    }
    
    printf("Python executable hash verification successful\n");
    return 1;
}

// 计算文件的SHA256哈希值
int calculate_file_hash(const char* file_path, char* hash_hex, size_t hex_size) {
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    HANDLE hFile = NULL;
    BYTE buffer[4096];
    DWORD bytesRead = 0;
    BYTE hash[32]; // SHA256哈希是32字节
    DWORD hashLen = 32;
    
    // 打开文件
    hFile = CreateFile(file_path, 
                       GENERIC_READ, 
                       FILE_SHARE_READ, 
                       NULL, 
                       OPEN_EXISTING, 
                       FILE_FLAG_SEQUENTIAL_SCAN, 
                       NULL);
    
    if (hFile == INVALID_HANDLE_VALUE) {
        printf("Failed to open file: %s (Error: %lu)\n", file_path, GetLastError());
        return 0;
    }
    
    // 获取加密服务提供程序
    if (!CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)) {
        printf("CryptAcquireContext failed (Error: %lu)\n", GetLastError());
        CloseHandle(hFile);
        return 0;
    }
    
    // 创建哈希对象
    if (!CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
        printf("CryptCreateHash failed (Error: %lu)\n", GetLastError());
        CryptReleaseContext(hProv, 0);
        CloseHandle(hFile);
        return 0;
    }
    
    // 读取文件并计算哈希
    while (ReadFile(hFile, buffer, sizeof(buffer), &bytesRead, NULL) && bytesRead > 0) {
        if (!CryptHashData(hHash, buffer, bytesRead, 0)) {
            printf("CryptHashData failed (Error: %lu)\n", GetLastError());
            CryptDestroyHash(hHash);
            CryptReleaseContext(hProv, 0);
            CloseHandle(hFile);
            return 0;
        }
    }
    
    // 获取哈希值
    if (!CryptGetHashParam(hHash, HP_HASHVAL, hash, &hashLen, 0)) {
        printf("CryptGetHashParam failed (Error: %lu)\n", GetLastError());
        CryptDestroyHash(hHash);
        CryptReleaseContext(hProv, 0);
        CloseHandle(hFile);
        return 0;
    }
    
    // 将哈希转换为十六进制字符串
    if (hex_size < 65) { // SHA256需要64个字符 + 空终止符
        printf("Buffer too small for hex string\n");
        CryptDestroyHash(hHash);
        CryptReleaseContext(hProv, 0);
        CloseHandle(hFile);
        return 0;
    }
    
    for (DWORD i = 0; i < hashLen; i++) {
        sprintf_s(&hash_hex[i * 2], hex_size - (i * 2), "%02x", hash[i]);
    }
    hash_hex[64] = '\0'; // 确保字符串正确终止
    
    // 清理资源
    CryptDestroyHash(hHash);
    CryptReleaseContext(hProv, 0);
    CloseHandle(hFile);
    
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
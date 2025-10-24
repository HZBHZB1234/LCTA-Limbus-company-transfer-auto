import sys
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

class ImageEnhancementApp:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title('图像局部暗化增强工具')
        self.window.geometry('1200x800')
        
        self.image = None
        self.processed_image = None
        self.original_photo = None
        self.processed_photo = None
        
        self.initUI()
        
    def initUI(self):
        # 创建主框架
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧图像显示区域
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 原始图像标签和画布
        ttk.Label(left_frame, text='原始图像').pack(anchor=tk.W)
        self.original_canvas = tk.Canvas(left_frame, relief=tk.SUNKEN, border=1)
        self.original_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 处理后的图像标签和画布
        ttk.Label(left_frame, text='处理后的图像').pack(anchor=tk.W)
        self.processed_canvas = tk.Canvas(left_frame, relief=tk.SUNKEN, border=1)
        self.processed_canvas.pack(fill=tk.BOTH, expand=True)
        
        # 右侧控制面板
        right_frame = ttk.Frame(main_frame, width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)  # 防止框架收缩
        
        # 文件操作组
        file_group = ttk.LabelFrame(right_frame, text="文件操作", padding=10)
        file_group.pack(fill=tk.X, pady=(0, 10))
        
        self.load_btn = ttk.Button(file_group, text='加载图像', command=self.load_image)
        self.load_btn.pack(fill=tk.X, pady=5)
        
        self.save_btn = ttk.Button(file_group, text='保存图像', command=self.save_image)
        self.save_btn.pack(fill=tk.X, pady=5)
        
        # 增强方法选择
        method_group = ttk.LabelFrame(right_frame, text="增强方法", padding=10)
        method_group.pack(fill=tk.X, pady=(0, 10))
        
        self.method_var = tk.StringVar()
        self.method_combo = ttk.Combobox(method_group, textvariable=self.method_var, state="readonly")
        self.method_combo['values'] = ("自适应直方图均衡化", "对比度受限自适应直方图均衡化", 
                                      "伽马校正", "同态滤波", "Retinex增强")
        self.method_combo.current(0)
        self.method_combo.pack(fill=tk.X, pady=5)
        self.method_combo.bind('<<ComboboxSelected>>', self.apply_enhancement)
        
        # 参数控制组
        params_group = ttk.LabelFrame(right_frame, text="参数调整", padding=10)
        params_group.pack(fill=tk.X)
        
        # 伽马值调整
        ttk.Label(params_group, text='伽马值: 1.0').pack(anchor=tk.W)
        self.gamma_var = tk.DoubleVar(value=1.0)
        self.gamma_scale = ttk.Scale(params_group, from_=0.01, to=3.0, variable=self.gamma_var, 
                                    orient=tk.HORIZONTAL, command=self.update_gamma_label)
        self.gamma_scale.pack(fill=tk.X, pady=(0, 10))
        
        # 对比度调整
        ttk.Label(params_group, text='对比度: 1.0').pack(anchor=tk.W)
        self.contrast_var = tk.DoubleVar(value=1.0)
        self.contrast_scale = ttk.Scale(params_group, from_=0.01, to=3.0, variable=self.contrast_var, 
                                       orient=tk.HORIZONTAL, command=self.update_contrast_label)
        self.contrast_scale.pack(fill=tk.X, pady=(0, 10))
        
        # 亮度调整
        ttk.Label(params_group, text='亮度: 0').pack(anchor=tk.W)
        self.brightness_var = tk.IntVar(value=0)
        self.brightness_scale = ttk.Scale(params_group, from_=-100, to=100, variable=self.brightness_var, 
                                         orient=tk.HORIZONTAL, command=self.update_brightness_label)
        self.brightness_scale.pack(fill=tk.X, pady=(0, 10))
        
        # 绑定滑动条事件
        self.gamma_scale.bind('<ButtonRelease-1>', self.apply_enhancement)
        self.contrast_scale.bind('<ButtonRelease-1>', self.apply_enhancement)
        self.brightness_scale.bind('<ButtonRelease-1>', self.apply_enhancement)
        
        # 绑定画布尺寸变化事件
        self.original_canvas.bind('<Configure>', self.on_canvas_resize)
        self.processed_canvas.bind('<Configure>', self.on_canvas_resize)
        
    def on_canvas_resize(self, event):
        # 当画布尺寸变化时重新显示图像
        if event.widget == self.original_canvas and self.image is not None:
            self.display_image(self.image, self.original_canvas)
        elif event.widget == self.processed_canvas and self.processed_image is not None:
            self.display_image(self.processed_image, self.processed_canvas)
        
    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.tif"),("所有文件", "*.*")])
        if file_path:
            try:
                # 使用imdecode处理可能的中文路径问题
                with open(file_path, 'rb') as f:
                    file_bytes = np.asarray(bytearray(f.read()), dtype=np.uint8)
                    self.image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            except Exception as e:
                messagebox.showerror("错误", f"加载图像时出错: {e}")
                return
                
            if self.image is not None:
                self.display_image(self.image, self.original_canvas)
                self.apply_enhancement()
            else:
                messagebox.showerror("错误", f"无法解码图像文件: {file_path}")
    
    def save_image(self):
        if self.processed_image is not None:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG图像", "*.png"), ("JPEG图像", "*.jpg *.jpeg")])
            if file_path:
                cv2.imwrite(file_path, self.processed_image)
                messagebox.showinfo("成功", "图像已保存")
    
    def update_gamma_label(self, value):
        for widget in self.gamma_scale.master.winfo_children():
            if isinstance(widget, ttk.Label) and widget.cget("text").startswith("伽马值:"):
                widget.config(text=f'伽马值: {float(value):.2f}')
                break
    
    def update_contrast_label(self, value):
        for widget in self.contrast_scale.master.winfo_children():
            if isinstance(widget, ttk.Label) and widget.cget("text").startswith("对比度:"):
                widget.config(text=f'对比度: {float(value):.2f}')
                break
    
    def update_brightness_label(self, value):
        for widget in self.brightness_scale.master.winfo_children():
            if isinstance(widget, ttk.Label) and widget.cget("text").startswith("亮度:"):
                widget.config(text=f'亮度: {int(float(value))}')
                break
    
    def apply_enhancement(self, event=None):
        if self.image is None:
            return
        
        method = self.method_var.get()
        gamma = self.gamma_var.get()
        contrast = self.contrast_var.get()
        brightness = self.brightness_var.get()
        
        # 应用基本的对比度和亮度调整
        img = cv2.convertScaleAbs(self.image, alpha=contrast, beta=brightness)
        
        # 应用选择的增强方法
        if method == "自适应直方图均衡化":
            # 转换为YUV颜色空间，对Y通道进行直方图均衡化
            img_yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            img_yuv[:, :, 0] = clahe.apply(img_yuv[:, :, 0])
            enhanced = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2BGR)
            
        elif method == "对比度受限自适应直方图均衡化":
            # 使用CLAHE
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            
        elif method == "伽马校正":
            # 应用伽马校正
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255
                             for i in np.arange(0, 256)]).astype("uint8")
            enhanced = cv2.LUT(img, table)
            
        elif method == "同态滤波":
            # 同态滤波处理
            enhanced = self.homomorphic_filter(img)
            
        elif method == "Retinex增强":
            # Retinex增强算法
            enhanced = self.retinex_enhancement(img)
            
        else:
            enhanced = img.copy()
        
        self.processed_image = enhanced
        self.display_image(enhanced, self.processed_canvas)
    
    def homomorphic_filter(self, img):
        # 转换为浮点数并进行对数变换
        img_float = np.float32(img) / 255.0
        rows, cols, channels = img_float.shape
        
        # 对每个通道应用同态滤波
        result = np.zeros_like(img_float)
        
        for channel in range(channels):
            channel_data = img_float[:, :, channel]
            
            # 对数变换
            log_channel = np.log(channel_data + 0.01)
            
            # 傅里叶变换
            fft = np.fft.fft2(log_channel)
            fft_shift = np.fft.fftshift(fft)
            
            # 创建同态滤波器
            D0 = 30
            gamma_h = 2.0
            gamma_l = 0.5
            c = 1
            
            u = np.arange(rows).reshape(-1, 1) - rows//2
            v = np.arange(cols) - cols//2
            D = np.sqrt(u**2 + v**2)
            H = (gamma_h - gamma_l) * (1 - np.exp(-c * (D**2 / D0**2))) + gamma_l
            
            # 应用滤波器
            filtered_fft = fft_shift * H
            
            # 逆傅里叶变换
            fft_ishift = np.fft.ifftshift(filtered_fft)
            filtered = np.fft.ifft2(fft_ishift)
            
            # 指数变换
            filtered_exp = np.exp(np.real(filtered))
            
            # 归一化到0-1范围
            filtered_exp = (filtered_exp - np.min(filtered_exp)) / (np.max(filtered_exp) - np.min(filtered_exp))
            result[:, :, channel] = filtered_exp
        
        # 转换回8位图像
        result = np.uint8(result * 255)
        return result
    
    def retinex_enhancement(self, img):
        # 简单的Retinex增强实现
        # 转换为浮点数
        img_float = np.float32(img) / 255.0
        
        # 计算每个通道的对数
        log_r = np.log(img_float[:, :, 2] + 0.01)
        log_g = np.log(img_float[:, :, 1] + 0.01)
        log_b = np.log(img_float[:, :, 0] + 0.01)
        
        # 高斯模糊作为照度估计
        sigma = 80
        illum_r = cv2.GaussianBlur(img_float[:, :, 2], (0, 0), sigma)
        illum_g = cv2.GaussianBlur(img_float[:, :, 1], (0, 0), sigma)
        illum_b = cv2.GaussianBlur(img_float[:, :, 0], (0, 0), sigma)
        
        # 反射分量计算
        ref_r = log_r - np.log(illum_r + 0.01)
        ref_g = log_g - np.log(illum_g + 0.01)
        ref_b = log_b - np.log(illum_b + 0.01)
        
        # 对比度拉伸
        def stretch_channel(channel):
            min_val = np.min(channel)
            max_val = np.max(channel)
            return (channel - min_val) / (max_val - min_val)
        
        ref_r = stretch_channel(ref_r)
        ref_g = stretch_channel(ref_g)
        ref_b = stretch_channel(ref_b)
        
        # 合并通道
        enhanced = np.stack([ref_b, ref_g, ref_r], axis=2)
        enhanced = np.uint8(enhanced * 255)
        
        return enhanced
    
    def display_image(self, img, canvas):
        # 获取画布的实际尺寸
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        # 如果画布尺寸太小，则跳过显示
        if canvas_width <= 1 or canvas_height <= 1:
            return
            
        # 调整图像大小以适应画布
        h, w = img.shape[:2]
        canvas_aspect_ratio = canvas_width / canvas_height
        img_aspect_ratio = w / h
        
        if img_aspect_ratio > canvas_aspect_ratio:
            new_w = canvas_width
            new_h = int(new_w / img_aspect_ratio)
        else:
            new_h = canvas_height
            new_w = int(new_h * img_aspect_ratio)
        
        # 调整图像大小
        img_resized = cv2.resize(img, (new_w, new_h))
        
        # 转换颜色空间从BGR到RGB
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        
        # 转换为PIL图像然后转换为ImageTk
        pil_img = Image.fromarray(img_rgb)
        photo = ImageTk.PhotoImage(pil_img)
        
        # 清除画布并显示新图像
        canvas.delete("all")
        canvas.create_image(canvas_width//2, canvas_height//2, 
                           anchor=tk.CENTER, image=photo)
        
        # 保持引用以防止垃圾回收
        if canvas == self.original_canvas:
            self.original_photo = photo
        else:
            self.processed_photo = photo

def main():
    root = tk.Tk()
    app = ImageEnhancementApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
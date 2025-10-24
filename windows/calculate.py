import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from math import comb, log, exp, lgamma, sqrt
import sys
from matplotlib import font_manager
import threading
import time
from queue import Queue

class GachaCalculator:
    def __init__(self, root__):
        self.root = tk.Toplevel(root__)
        self.root.title("边狱公司抽卡概率计算器")
        self.root.geometry("1000x800")
        
        # 设置中文字体
        try:
            # 尝试使用系统支持的中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            pass
        
        # 概率常量
        self.p_2nd = 0.129  # 二级概率
        self.p_3rd = 0.029  # 三级概率
        self.p_ego = 0.013  # ego概率
        self.p_announcer = 0.013  # 播报员概率
        self.p_1st = 1 - (self.p_2nd + self.p_3rd + self.p_ego + self.p_announcer)  # 一级概率
        
        # 存储计算结果
        self.calculation_results = {}
        
        # 计算队列和线程
        self.calculation_queue = Queue()
        self.calculation_thread = None
        self.calculation_running = False
        
        self.setup_ui()
    
    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 输入区域
        input_frame = ttk.LabelFrame(main_frame, text="输入参数", padding="5")
        input_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 抽取次数
        ttk.Label(input_frame, text="抽取次数:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.times_var = tk.StringVar(value="100")
        times_entry = ttk.Entry(input_frame, textvariable=self.times_var, width=10)
        times_entry.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        # 计算目标选择
        ttk.Label(input_frame, text="图表显示:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.chart_target_var = tk.StringVar(value="三级")
        chart_target_combo = ttk.Combobox(input_frame, textvariable=self.chart_target_var, 
                                        values=["二级", "三级", "ego", "播报员", "全部"], width=8)
        chart_target_combo.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # up角色数量
        ttk.Label(input_frame, text="UP角色数量:").grid(row=2, column=0, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="二级UP:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.up_2nd_var = tk.StringVar(value="3")
        up_2nd_entry = ttk.Entry(input_frame, textvariable=self.up_2nd_var, width=5)
        up_2nd_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="三级UP:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.up_3rd_var = tk.StringVar(value="2")
        up_3rd_entry = ttk.Entry(input_frame, textvariable=self.up_3rd_var, width=5)
        up_3rd_entry.grid(row=4, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="ego UP:").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.up_ego_var = tk.StringVar(value="1")
        up_ego_entry = ttk.Entry(input_frame, textvariable=self.up_ego_var, width=5)
        up_ego_entry.grid(row=5, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="播报员UP:").grid(row=6, column=0, sticky=tk.W, pady=2)
        self.up_announcer_var = tk.StringVar(value="1")
        up_announcer_entry = ttk.Entry(input_frame, textvariable=self.up_announcer_var, width=5)
        up_announcer_entry.grid(row=6, column=1, sticky=tk.W, pady=2)
        
        # 目标数量设置
        ttk.Label(input_frame, text="目标数量:").grid(row=7, column=0, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="二级目标:").grid(row=8, column=0, sticky=tk.W, pady=2)
        self.target_2nd_var = tk.StringVar(value="1")
        target_2nd_entry = ttk.Entry(input_frame, textvariable=self.target_2nd_var, width=5)
        target_2nd_entry.grid(row=8, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="三级目标:").grid(row=9, column=0, sticky=tk.W, pady=2)
        self.target_3rd_var = tk.StringVar(value="1")
        target_3rd_entry = ttk.Entry(input_frame, textvariable=self.target_3rd_var, width=5)
        target_3rd_entry.grid(row=9, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="ego目标:").grid(row=10, column=0, sticky=tk.W, pady=2)
        self.target_ego_var = tk.StringVar(value="1")
        target_ego_entry = ttk.Entry(input_frame, textvariable=self.target_ego_var, width=5)
        target_ego_entry.grid(row=10, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="播报员目标:").grid(row=11, column=0, sticky=tk.W, pady=2)
        self.target_announcer_var = tk.StringVar(value="1")
        target_announcer_entry = ttk.Entry(input_frame, textvariable=self.target_announcer_var, width=5)
        target_announcer_entry.grid(row=11, column=1, sticky=tk.W, pady=2)
        
        # 选填参数
        ttk.Label(input_frame, text="选填参数:").grid(row=12, column=0, sticky=tk.W, pady=2)
        
        ttk.Label(input_frame, text="已抽取ego百分比:").grid(row=13, column=0, sticky=tk.W, pady=2)
        self.ego_percent_var = tk.StringVar(value="0")
        ego_percent_entry = ttk.Entry(input_frame, textvariable=self.ego_percent_var, width=5)
        ego_percent_entry.grid(row=13, column=1, sticky=tk.W, pady=2)
        
        # 模式选择
        ttk.Label(input_frame, text="计算模式:").grid(row=14, column=0, sticky=tk.W, pady=2)
        self.mode_var = tk.StringVar(value="按次数计算")
        mode_combo = ttk.Combobox(input_frame, textvariable=self.mode_var, 
                                 values=["按次数计算", "按目标绘制"], width=12)
        mode_combo.grid(row=14, column=1, sticky=tk.W, pady=2)
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="计算概率", command=self.start_calculation).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="清除结果", command=self.clear).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="更新图表", command=self.update_chart).pack(side=tk.LEFT, padx=5)
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.progress.grid_remove()  # 初始隐藏
        
        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        
        # 结果显示区域
        result_frame = ttk.LabelFrame(main_frame, text="计算结果", padding="5")
        result_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.result_text = tk.Text(result_frame, height=10, width=70)
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 图表区域
        self.figure = plt.Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=main_frame)
        self.canvas.get_tk_widget().grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # 配置权重使UI元素可扩展
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        # 启动队列检查
        self.check_queue()
    
    def log_comb(self, n, k):
        """使用对数计算组合数，避免大数溢出"""
        if k < 0 or k > n:
            return -float('inf')
        return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
    
    def cal_exact(self, times, proper, need):
        """使用对数空间计算二项分布概率，提高数值稳定性"""
        if proper <= 0 or proper >= 1:
            return 0.0 if need > 0 else 1.0
            
        # 使用对数计算避免数值下溢
        log_prob = self.log_comb(times, need) + need * log(proper) + (times - need) * log(1 - proper)
        return exp(log_prob)
    
    def normal_approximation(self, times, proper, need):
        """使用正态近似计算二项分布概率，适用于大数情况"""
        if proper <= 0 or proper >= 1:
            return 0.0 if need > 0 else 1.0
            
        # 计算均值和标准差
        mean = times * proper
        std_dev = sqrt(times * proper * (1 - proper))
        
        # 使用连续性校正
        if need <= mean:
            # 计算P(X >= need) = 1 - P(X < need) ≈ 1 - Φ((need - 0.5 - mean)/std_dev)
            z = (need - 0.5 - mean) / std_dev
            from scipy.stats import norm
            return 1 - norm.cdf(z)
        else:
            # 计算P(X >= need) ≈ 1 - Φ((need - 0.5 - mean)/std_dev)
            z = (need - 0.5 - mean) / std_dev
            from scipy.stats import norm
            return 1 - norm.cdf(z)
    
    def cal_probability_optimized(self, times, proper, target_count):
        """优化版本的概率计算，自动选择合适的方法"""
        # 对于小次数或极端概率，使用精确计算
        if times <= 1000 or proper < 0.001 or proper > 0.999:
            prob = 0.0
            # 使用累积计算，避免重复计算对数组合数
            log_proper = log(proper)
            log_1_minus_proper = log(1 - proper)
            
            # 从目标数量开始计算
            for i in range(target_count, times + 1):
                log_prob = self.log_comb(times, i) + i * log_proper + (times - i) * log_1_minus_proper
                prob += exp(log_prob)
            return prob
        else:
            # 对于大次数，使用正态近似
            try:
                return self.normal_approximation(times, proper, target_count)
            except:
                # 如果正态近似失败，回退到精确计算
                prob = 0.0
                log_proper = log(proper)
                log_1_minus_proper = log(1 - proper)
                
                # 只计算主要贡献区域，提高效率
                mean = times * proper
                std_dev = sqrt(times * proper * (1 - proper))
                start = max(target_count, int(mean - 4 * std_dev))
                end = min(times, int(mean + 4 * std_dev))
                
                for i in range(start, end + 1):
                    log_prob = self.log_comb(times, i) + i * log_proper + (times - i) * log_1_minus_proper
                    prob += exp(log_prob)
                return prob
    
    def calculate_all_targets(self, times, up_counts, ego_percent, target_counts):
        """计算所有目标的概率"""
        results = {}
        targets = ["二级", "三级", "ego", "播报员"]
        base_probs = [self.p_2nd, self.p_3rd, self.p_ego, self.p_announcer]
        
        for i, target in enumerate(targets):
            target_count = target_counts[i]
            if target_count > 0:  # 只计算目标数量大于0的
                base_prob = base_probs[i]
                up_count = up_counts[i]
                
                # 特殊处理 ego 的已抽取百分比
                if target == "ego":
                    # 计算已获得的非up ego数量
                    total_non_up_ego = 50  # 假设总ego数量为50
                    obtained_non_up_ego = (ego_percent / 100) * (total_non_up_ego - up_count)
                    remaining_non_up_ego = total_non_up_ego - up_count - obtained_non_up_ego
                    
                    # 计算实际概率 (50% up池, 50% 全池)
                    # up池中的概率: 0.5 * (1/up_count)
                    # 全池中的概率: 0.5 * (1/(remaining_non_up_ego + up_count))
                    actual_prob = 0.5 * (1/up_count) + 0.5 * (1/(remaining_non_up_ego + up_count))
                    
                    # 乘以基础ego概率
                    actual_prob *= base_prob
                else:
                    # 计算实际概率 (50% up池, 50% 全池)
                    total_chars = 50  # 假设总角色数为50
                    actual_prob = base_prob * (0.5 * (1 / up_count) + 0.5 * (1 / total_chars))

                # 如果UP数量为0，视为无视该种类，概率为0
                if up_count == 0:
                    continue

                # 计算至少获得target_count个的概率
                prob = self.cal_probability_optimized(times, actual_prob, target_count)
                results[target] = prob

                # 计算概率分布
                x_vals = list(range(0, min(times + 1, 51)))  # 限制显示范围
                y_vals = []
                for k in x_vals:
                    if k == 0:
                        # P(X=0) = (1-p)^n
                        y_vals.append(exp(times * log(1 - actual_prob)))
                    else:
                        y_vals.append(self.cal_exact(times, actual_prob, k))
                results[f"{target}_dist"] = (x_vals, y_vals)
        
        return results
    
    def start_calculation(self):
        """启动计算线程"""
        if self.calculation_running:
            return
            
        try:
            # 获取输入值
            times = int(self.times_var.get())
            up_2nd = int(self.up_2nd_var.get())
            up_3rd = int(self.up_3rd_var.get())
            up_ego = int(self.up_ego_var.get())
            up_announcer = int(self.up_announcer_var.get())
            ego_percent = float(self.ego_percent_var.get())
            target_2nd = int(self.target_2nd_var.get())
            target_3rd = int(self.target_3rd_var.get())
            target_ego = int(self.target_ego_var.get())
            target_announcer = int(self.target_announcer_var.get())
            mode = self.mode_var.get()
            
            # 显示进度条
            self.progress.grid()
            self.progress.start()
            self.status_var.set("计算中...")
            self.calculation_running = True
            
            # 启动计算线程
            self.calculation_thread = threading.Thread(
                target=self.calculate_thread,
                args=(times, up_2nd, up_3rd, up_ego, up_announcer, ego_percent, 
                      target_2nd, target_3rd, target_ego, target_announcer, mode)
            )
            self.calculation_thread.daemon = True
            self.calculation_thread.start()
                
        except ValueError as e:
            messagebox.showerror("输入错误", "请检查输入值是否为有效数字")
        except Exception as e:
            messagebox.showerror("错误", f"计算过程中发生错误: {str(e)}")
    
    def calculate_thread(self, times, up_2nd, up_3rd, up_ego, up_announcer, ego_percent, 
                        target_2nd, target_3rd, target_ego, target_announcer, mode):
        """计算线程"""
        try:
            up_counts = (up_2nd, up_3rd, up_ego, up_announcer)
            target_counts = (target_2nd, target_3rd, target_ego, target_announcer)
            
            if mode == "按次数计算":
                # 计算所有目标的概率
                results = self.calculate_all_targets(times, up_counts, ego_percent, target_counts)
                
                # 将结果放入队列
                self.calculation_queue.put(("results", results, times, up_counts, target_counts))
                
            else:  # 按目标绘制模式
                # 计算不同抽取次数下达到目标的概率
                max_times = 1000  # 最大计算次数
                step = max(1, times // 100)  # 动态步长
                targets = ["二级", "三级", "ego", "播报员"]
                colors = ['red', 'blue', 'green', 'purple']
                
                plot_data = {}
                result_text = ""
                
                for i, target in enumerate(targets):
                    target_count = target_counts[i]
                    if target_count > 0:  # 只计算目标数量大于0的
                        x_vals = list(range(target_count, max_times+1, step))
                        y_vals = []
                        
                        for j, t in enumerate(x_vals):
                            # 更新进度
                            if j % 10 == 0:
                                self.calculation_queue.put(("progress", f"计算{target}进度: {j}/{len(x_vals)}"))
                            
                            prob = self.cal_probability_optimized(t, 
                                self.get_target_probability(target, up_counts, ego_percent), 
                                target_count)
                            y_vals.append(prob)
                            if prob >= 0.99:  # 概率达到99%时停止计算
                                x_vals = x_vals[:len(y_vals)]
                                break
                        
                        plot_data[target] = (x_vals, y_vals, colors[i])
                        
                        # 找到达到90%概率所需的次数
                        for j, prob in enumerate(y_vals):
                            if prob >= 0.9:
                                result_text += f"{target}达到90%概率所需抽取次数: {x_vals[j]}\n"
                                break
                
                self.calculation_queue.put(("plot", plot_data, result_text))
                
        except Exception as e:
            self.calculation_queue.put(("error", str(e)))
    
    def get_target_probability(self, target, up_counts, ego_percent):
        """获取目标的基准概率"""
        if target == "二级":
            base_prob = self.p_2nd
            up_count = up_counts[0]
            total_chars = 50
            return base_prob * (0.5 * (1/up_count) + 0.5 * (1/total_chars))
        elif target == "三级":
            base_prob = self.p_3rd
            up_count = up_counts[1]
            total_chars = 50
            return base_prob * (0.5 * (1/up_count) + 0.5 * (1/total_chars))
        elif target == "ego":
            base_prob = self.p_ego
            up_count = up_counts[2]
            # 计算已获得的非up ego数量
            total_non_up_ego = 50  # 假设总ego数量为50
            obtained_non_up_ego = (ego_percent / 100) * (total_non_up_ego - up_count)
            remaining_non_up_ego = total_non_up_ego - up_count - obtained_non_up_ego
            
            # 计算实际概率 (50% up池, 50% 全池)
            actual_prob = 0.5 * (1/up_count) + 0.5 * (1/(remaining_non_up_ego + up_count))
            return base_prob * actual_prob
        elif target == "播报员":
            base_prob = self.p_announcer
            up_count = up_counts[3]
            total_chars = 50
            return base_prob * (0.5 * (1/up_count) + 0.5 * (1/total_chars))
        else:
            return 0
    
    def check_queue(self):
        """检查计算队列，更新UI"""
        try:
            while not self.calculation_queue.empty():
                item = self.calculation_queue.get_nowait()
                
                if item[0] == "results":
                    _, results, times, up_counts, target_counts = item
                    self.calculation_results = results
                    
                    # 显示结果
                    self.result_text.delete(1.0, tk.END)
                    for target, prob in self.calculation_results.items():
                        if not target.endswith("_dist"):
                            target_index = ["二级", "三级", "ego", "播报员"].index(target)
                            self.result_text.insert(tk.END, 
                                f"获得至少{target_counts[target_index]}个{target}的概率: {prob*100:.6f}%\n")
                    
                    # 绘制图表
                    self.update_chart()
                    
                elif item[0] == "plot":
                    _, plot_data, result_text = item
                    
                    self.result_text.delete(1.0, tk.END)
                    self.result_text.insert(tk.END, result_text)
                    
                    # 绘制图表
                    self.figure.clear()
                    ax = self.figure.add_subplot(111)
                    
                    for target, (x_vals, y_vals, color) in plot_data.items():
                        ax.plot(x_vals, y_vals, color=color, label=f'{target}')
                    
                    ax.set_xlabel('抽取次数')
                    ax.set_ylabel('概率')
                    ax.set_title('获得目标数量的概率随抽取次数变化')
                    ax.grid(True)
                    ax.legend()
                    self.figure.tight_layout()
                    self.canvas.draw()
                    
                elif item[0] == "progress":
                    _, message = item
                    self.status_var.set(message)
                    
                elif item[0] == "error":
                    _, error_msg = item
                    messagebox.showerror("错误", f"计算过程中发生错误: {error_msg}")
                
                self.calculation_queue.task_done()
                
        except:
            pass
            
        # 停止进度条
        if self.calculation_queue.empty() and self.calculation_running:
            self.progress.stop()
            self.progress.grid_remove()
            self.status_var.set("计算完成")
            self.calculation_running = False
            
        # 继续检查队列
        self.root.after(100, self.check_queue)
    
    def update_chart(self):
        """更新图表显示"""
        if not self.calculation_results:
            return
            
        chart_target = self.chart_target_var.get()
        self.figure.clear()
        
        if chart_target == "全部":
            # 创建2x2的子图网格
            axes = self.figure.subplots(2, 2)
            axes = axes.flatten()
            
            targets = ["二级", "三级", "ego", "播报员"]
            colors = ['red', 'blue', 'green', 'purple']
            
            for i, target in enumerate(targets):
                if f"{target}_dist" in self.calculation_results:
                    x_vals, y_vals = self.calculation_results[f"{target}_dist"]
                    # 跳过0个的情况（第一个元素）
                    #x_vals = x_vals[1:]
                    #y_vals = y_vals[1:]
                    
                    axes[i].bar(x_vals, y_vals, color=colors[i], alpha=0.7)
                    axes[i].set_xlabel('获得数量')
                    axes[i].set_ylabel('概率')
                    axes[i].set_title(f'{target}获得数量概率分布')
                    
                    # 添加数值标注（只标注概率较高的几个点）
                    max_val = max(y_vals) if y_vals else 0
                    for j, (x, y) in enumerate(zip(x_vals, y_vals)):
                        if y > max_val * 0.1 and max_val > 0:  # 只标注概率大于最大值10%的点
                            # 在柱子上方显示概率
                            axes[i].text(x, y + 0.01, f'{y:.2%}', ha='center', va='bottom', fontsize=8)
                            # 在柱子下方显示数量
                            axes[i].text(x, -0.02, str(x), ha='center', va='top', fontsize=8)
            
            self.figure.tight_layout()
            
        else:
            # 显示单个目标的图表
            ax = self.figure.add_subplot(111)
            
            if f"{chart_target}_dist" in self.calculation_results:
                x_vals, y_vals = self.calculation_results[f"{chart_target}_dist"]
                # 跳过0个的情况（第一个元素）
                #x_vals = x_vals[1:]
                #y_vals = y_vals[1:]
                
                bars = ax.bar(x_vals, y_vals, alpha=0.7)
                ax.set_xlabel('获得数量')
                ax.set_ylabel('概率')
                ax.set_title(f'{chart_target}获得数量概率分布')
                
                # 添加数值标注
                max_val = max(y_vals) if y_vals else 0
                for i, (x, y) in enumerate(zip(x_vals, y_vals)):
                    if y > max_val * 0.1 and max_val > 0:  # 只标注概率大于最大值10%的点
                        # 在柱子上方显示概率
                        ax.text(x, y + 0.01, f'{y:.2%}', ha='center', va='bottom', fontsize=8)
                        # 在柱子下方显示数量
                        ax.text(x, -0.02, str(x), ha='center', va='top', fontsize=8)
            
            self.figure.tight_layout()
        
        self.canvas.draw()
    
    def clear(self):
        self.result_text.delete(1.0, tk.END)
        self.figure.clear()
        self.canvas.draw()
        self.calculation_results = {}

if __name__ == "__main__":
    root = tk.Tk()
    app = GachaCalculator(root)
    root.mainloop()
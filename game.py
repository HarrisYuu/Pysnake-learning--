"""
Pysnake —— 经典贪吃蛇大作战
============================

程序结构（自上而下）：
  1. 常量区        —— 所有可调参数（格子大小、速度等）集中放在这里
  2. 工具函数      —— 排行榜文件的读取/保存、按钮样式工厂
  3. PysnakeApp    —— 总控制器：管理三个界面（标题/游戏/排行榜）的切换与 ESC 退出
  4. TitleScreen   —— 开始界面（START / SCORE / EXIT）
  5. ScoreScreen   —— 排行榜界面（查看 / 删除 / 清空 / 返回）
  6. GameScreen    —— 游戏主逻辑（玩家蛇、NPC 蛇、食物、金苹果、小火箭、绘制）

学习要点：
  * tkinter 的 Canvas 画图：所有元素（矩形、圆、文字）都是"画布上的对象"，
    用 create_xxx 创建、delete 删除、create_window 嵌入控件。
  * 网格坐标 vs 像素坐标：游戏逻辑全部用"第几格"(0~29, 0~19) 思考，
    只有绘制时才换算成像素 (x*CELL_SIZE)。
  * 游戏循环：用 root.after(毫秒, 函数) 让函数周期性自我调用，形成循环。
  * 界面切换：多个 Frame 叠在一起，谁调用 tkraise() 谁就显示在最上层。
"""

import json
import math
import os
import random
import time
import tkinter as tk
from tkinter import messagebox  # 弹窗（确认框/提示框）

# ==================== 1. 常量区 ====================
# 把所有"魔法数字"集中在这里，想调难度改这里就行

CELL_SIZE = 20          # 每格边长（像素）
GRID_WIDTH = 30         # 横向格数 → 画布宽 30*20 = 600 像素
GRID_HEIGHT = 20        # 纵向格数 → 画布高 20*20 = 400 像素
GAME_SPEED = 120        # 每隔多少毫秒走一步（越小蛇越快）
NPC_RESPAWN_MS = 3000   # NPC 蛇被击杀后，多少毫秒重生

# 小火箭道具参数
ROCKET_SPAWN_MIN = 8000   # 火箭尝试出现的最短间隔（毫秒）
ROCKET_SPAWN_MAX = 15000  # 最长间隔（毫秒）
BOOST_DURATION = 3.0      # 加速持续时间（秒）
BOOST_FACTOR = 2          # 速度倍数（2 = 翻倍）

# 棋盘格背景的两格交替颜色（深绿系）
BG_DARK = "#16281a"
BG_LIGHT = "#1b331f"

# 排行榜 JSON 文件的存放路径：
# os.path.abspath(__file__) 是当前 .py 文件的绝对路径，取其所在目录，
# 保证 json 文件和游戏放在一起，无论从哪里启动程序都能找到
SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pysnake_scores.json")


# ==================== 2. 工具函数 ====================

def load_scores():
    """从 json 文件读取排行榜；文件不存在或损坏时返回空列表，保证程序不崩溃。"""
    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):  # 简单校验：必须是列表才可信
            return data
    except (OSError, json.JSONDecodeError):
        # OSError：文件不存在等；JSONDecodeError：文件内容不是合法 json
        pass
    return []


def save_scores_to_file(scores):
    """把排行榜写入 json 文件。ensure_ascii=False 让中文用户名原样保存。"""
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 写入失败（如目录只读）就静默跳过，不影响游戏


def make_button(parent, text, command, color="#2e7d32", width=16):
    """按钮样式工厂：统一配色，免得每个按钮写一长串参数。

    parent   —— 按钮放在哪个容器里
    text     —— 按钮文字
    command  —— 点击后调用哪个函数（注意：传的是函数本身，不加括号）
    color    —— 背景色
    """
    return tk.Button(
        parent, text=text, command=command, width=width,
        bg=color, fg="white",                    # 背景色 / 文字色
        activebackground="#43a047",              # 按下时的颜色
        activeforeground="white",
        font=("Microsoft YaHei", 13, "bold"),
        relief="flat",                           # 扁平风格，没有立体边框
        cursor="hand2",                          # 鼠标悬停变成手型
        pady=6,
    )


# ==================== 3. 总控制器 ====================

class PysnakeApp:
    """整个程序的"调度中心"，本身不负责具体界面，只负责切换界面。

    三个界面都是 tk.Frame（矩形容器），用 grid() 叠放在同一位置，
    调用谁的 tkraise()，谁就显示在最上层——这就是多界面切换的原理。

    全局按键（ESC）也在这里统一处理：
      标题界面按 ESC → 退出程序
      游戏 / 排行榜界面按 ESC → 返回标题界面
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Pysnake")
        self.root.resizable(False, False)      # 禁止拖拽改变窗口大小
        self.root.configure(bg="#0d1f12")      # 窗口背景色（深绿黑）

        self.scores = load_scores()            # 启动时读入本地排行榜
        self.game_active = False               # 当前是否在游戏界面（用于按键分发）
        self.current = "title"                 # 当前显示的界面名（ESC 判断用）

        # container 是三个界面共用的"托盘"
        self.container = tk.Frame(root, bg="#0d1f12")
        self.container.pack(fill="both", expand=True)

        # 创建三个界面，各自持有 app 引用，方便回调（如"返回"按钮）
        self.title_screen = TitleScreen(self.container, self)
        self.game_screen = GameScreen(self.container, self)
        self.score_screen = ScoreScreen(self.container, self)
        # 三者叠放在 (0,0)， sticky="nsew" 表示撑满整个托盘
        for frame in (self.title_screen, self.game_screen, self.score_screen):
            frame.grid(row=0, column=0, sticky="nsew")

        # 键盘事件统一绑定在根窗口上，再分发给游戏界面处理
        self.root.bind("<KeyPress>", self.on_key_press)
        self.show_title()

    def on_key_press(self, event):
        """全局按键分发：先处理 ESC，其余按键只在游戏界面才交给游戏。"""
        # 如果焦点在输入框（如游戏结束后的用户名输入框）里，
        # 按键只归输入框使用——否则打字敲到 r 会被当成"重开游戏"，
        # 敲到空格会暂停，敲到 q 会用火箭
        if isinstance(event.widget, tk.Entry):
            return
        if event.keysym == "Escape":
            if self.current == "title":
                self.root.destroy()   # 标题界面按 ESC = 退出程序
            else:
                self.show_title()     # 游戏/排行榜按 ESC = 返回标题
            return
        if self.game_active:
            self.game_screen.on_key_press(event)
        # event.keysym 就是按键名，如 "Up" / "space" / "q"

    # ---- 界面切换三件套 ----
    def show_title(self):
        self.game_active = False
        self.current = "title"
        self.title_screen.tkraise()            # 标题界面置顶显示

    def show_game(self):
        self.game_screen.start_game()          # 每次进游戏都重置一局
        self.game_active = True
        self.current = "game"
        self.game_screen.tkraise()

    def show_scores(self):
        self.game_active = False
        self.current = "scores"
        self.score_screen.refresh()            # 显示前刷新列表内容
        self.score_screen.tkraise()

    def save_score_record(self, name, score):
        """把一条成绩追加进内存列表，按分数降序排序，再写回文件。"""
        self.scores.append({
            "name": name,
            "score": score,
            "date": time.strftime("%Y-%m-%d %H:%M"),  # 当前时间格式化
        })
        self.scores.sort(key=lambda r: r["score"], reverse=True)
        save_scores_to_file(self.scores)


# ==================== 4. 开始界面 ====================

class TitleScreen(tk.Frame):
    """开始界面：标题 + 装饰蛇 + 三个按钮。全部是静态内容，没有逻辑。"""

    def __init__(self, master, app):
        super().__init__(master, bg="#0d1f12")
        self.app = app

        canvas = tk.Canvas(self, width=GRID_WIDTH * CELL_SIZE, height=360,
                           bg="#0d1f12", highlightthickness=0)
        canvas.pack()

        # ---- 用一串圆画一条装饰蛇（正弦曲线摆动的身体）----
        # reversed 让尾巴先画、头后画，头盖在尾巴上，层次更自然
        points = [
            (90 + i * 48, 280 - math.sin(i * 0.85) * 45)
            for i in range(10)
        ]
        for i, (x, y) in enumerate(reversed(points[:-1])):
            shade = ["#1b5e20", "#2e7d32", "#388e3c", "#43a047"][i % 4]
            canvas.create_oval(x - 14, y - 14, x + 14, y + 14, fill=shade, outline="")
        # 蛇头：大圆 + 两只眼睛（白眼珠 + 黑瞳孔）
        hx, hy = points[-1]
        canvas.create_oval(hx - 16, hy - 16, hx + 16, hy + 16, fill="#66bb6a", outline="")
        canvas.create_oval(hx - 6, hy - 6, hx + 2, hy + 2, fill="white", outline="")
        canvas.create_oval(hx + 4, hy - 6, hx + 12, hy + 2, fill="white", outline="")
        canvas.create_oval(hx - 3, hy - 3, hx, hy, fill="black", outline="")
        canvas.create_oval(hx + 7, hy - 3, hx + 10, hy, fill="black", outline="")
        # 蛇前方放一颗苹果（果身 + 果柄）
        canvas.create_oval(hx + 22, hy + 4, hx + 42, hy + 24, fill="#e0342f", outline="")
        canvas.create_line(hx + 32, hy + 4, hx + 33, hy - 3, fill="#7a4a21", width=2)

        # ---- 标题文字 ----
        canvas.create_text(
            GRID_WIDTH * CELL_SIZE / 2, 110, text="Pysnake",
            fill="#7CFC00", font=("Arial", 56, "bold"),
        )
        canvas.create_text(
            GRID_WIDTH * CELL_SIZE / 2, 165, text="经 典 贪 吃 蛇 大 作 战",
            fill="#a5d6a7", font=("Microsoft YaHei", 15),
        )

        # ---- 三个主按钮 ----
        # command 传的是"函数本身"（self.app.show_game），不是调用结果
        btns = tk.Frame(self, bg="#0d1f12", pady=14)
        btns.pack()
        make_button(btns, "START", app.show_game).pack(pady=6)
        make_button(btns, "SCORE", app.show_scores, color="#1565c0").pack(pady=6)
        make_button(btns, "EXIT", app.root.destroy, color="#b71c1c").pack(pady=6)


# ==================== 5. 排行榜界面 ====================

class ScoreScreen(tk.Frame):
    """排行榜界面：列表 + 三个操作按钮。"""

    def __init__(self, master, app):
        super().__init__(master, bg="#0d1f12")
        self.app = app

        tk.Label(self, text="排行榜", bg="#0d1f12", fg="#7CFC00",
                 font=("Microsoft YaHei", 26, "bold")).pack(pady=(18, 8))

        # Listbox（列表框）+ Scrollbar（滚动条）的经典组合：
        # 滚动条通过 command/yscrollcommand 与列表框"双向绑定"
        list_frame = tk.Frame(self, bg="#0d1f12")
        list_frame.pack()
        self.listbox = tk.Listbox(
            list_frame, width=52, height=14, font=("Consolas", 12),
            bg="#10241a", fg="#e8f5e9", selectbackground="#2e7d32",
            highlightthickness=0, activestyle="none",
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left")
        scrollbar.pack(side="left", fill="y")

        btns = tk.Frame(self, bg="#0d1f12", pady=14)
        btns.pack()
        make_button(btns, "删除选中", self.delete_selected, color="#e65100", width=12) \
            .pack(side="left", padx=8)
        make_button(btns, "清空全部", self.clear_all, color="#b71c1c", width=12) \
            .pack(side="left", padx=8)
        make_button(btns, "返回", app.show_title, color="#1565c0", width=12) \
            .pack(side="left", padx=8)

    def refresh(self):
        """根据内存里的 self.app.scores 重新填充列表。

        curselection 返回的是"显示行号"，而我们的列表与 scores 一一对应，
        所以行号就是下标，删除时直接用。
        """
        self.listbox.delete(0, "end")  # 清空旧内容
        if not self.app.scores:
            self.listbox.insert("end", "  暂无记录，快去 START 打一局吧！")
            return
        for i, rec in enumerate(self.app.scores):
            # :>3 右对齐占3位、:<12 左对齐占12位，让列表上下对齐
            self.listbox.insert(
                "end",
                f"  {i + 1:>3}. {rec['name']:<12} {rec['score']:>8} 分   {rec['date']}",
            )

    def delete_selected(self):
        selection = self.listbox.curselection()  # 返回选中的行号元组
        if not selection:
            messagebox.showinfo("提示", "请先选中一条记录")
            return
        index = selection[0]
        if index < len(self.app.scores):   # 防御："暂无记录"那行不可删
            del self.app.scores[index]     # 先改内存
            save_scores_to_file(self.app.scores)  # 再写回文件
            self.refresh()

    def clear_all(self):
        if not self.app.scores:
            return
        # askyesno 弹出"是/否"确认框，防止误触清空
        if messagebox.askyesno("确认", "确定要清空所有排行榜数据吗？"):
            self.app.scores.clear()
            save_scores_to_file(self.app.scores)
            self.refresh()


# ==================== 6. 游戏界面（核心） ====================

class GameScreen(tk.Frame):
    """游戏主界面：一块画布 + 底部状态栏。

    最重要的成员变量（游戏状态的"真相"都存这里）：
      self.snake    —— 玩家蛇，列表，[0] 是头，每项是 (x, y) 格子坐标
      self.npc      —— NPC 蛇，结构同上；空列表 [] 表示已死亡
      self.direction          —— 当前移动方向 (dx, dy)，如 (1,0)=向右
      self.pending_direction  —— 按键缓存的方向，下一步才生效
      self.food / self.golden / self.rocket —— 三种道具的格子位置（None = 场上没有）
      self.shield   —— 金苹果免疫是否就绪（可免一次撞墙或撞 NPC 的死亡）
      self.has_rocket  —— 玩家是否已拾取火箭（按 Q 使用）
      self.boost_until —— 加速截止时间戳（time.time() 秒），未到时刻就在加速中
      self.epoch    —— "时代编号"，每次重开 +1，用于让过期的定时任务自动作废
    """

    def __init__(self, master, app):
        super().__init__(master, bg="black")
        self.app = app
        self.epoch = 0
        self.npc = []              # 初始没有 NPC，start_game 里生成
        self.game_over_ui = []     # 游戏结束时临时创建的控件，重开时要清理

        # 初始状态默认值：__init__ 末尾就会启动 game_loop() 并调用 draw()，
        # 而 start_game() 要到点击 START 才执行，所以这些变量必须先在这里
        # 给默认值，否则第一次 draw() 就会报 AttributeError
        self.snake = []
        self.npc_direction = (1, 0)
        self.direction = (1, 0)
        self.pending_direction = (1, 0)
        self.food = None
        self.golden = None
        self.rocket = None
        self.shield = False
        self.has_rocket = False
        self.boost_until = 0.0
        self.score = 0
        self.paused = False
        self.game_over = False
        self.saved = False

        # ---- 画布：所有游戏画面都画在这块 600x400 的画布上 ----
        self.canvas = tk.Canvas(
            self, width=GRID_WIDTH * CELL_SIZE, height=GRID_HEIGHT * CELL_SIZE,
            bg="black", highlightthickness=0,
        )
        self.canvas.pack()

        # ---- 底部状态栏 ----
        self.score_label = tk.Label(
            self, bg="black", fg="white",
            font=("Microsoft YaHei", 10),
            text="方向键移动  空格暂停  Q使用火箭  击杀NPC蛇 +1000分",
        )
        self.score_label.pack(fill="x")

        self.draw_background()
        self.game_loop()  # 启动游戏循环（构造时就开始，内部用 after 自我续期）

    # ---------- 6.1 生命周期 ----------

    def start_game(self):
        """（重）开一局：把所有状态恢复到初始值。"""
        self.epoch += 1                    # 旧定时任务（NPC重生/道具）因 epoch 过期而失效
        self.clear_game_over_ui()          # 清掉上一局的输入框、按钮
        # 玩家蛇：横向三格，位于屏幕中央
        cx, cy = GRID_WIDTH // 2, GRID_HEIGHT // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.direction = (1, 0)            # 初始向右
        self.pending_direction = (1, 0)
        self.golden = None                 # 场上没有金苹果
        self.rocket = None                 # 场上没有火箭
        self.shield = False                # 免疫未激活
        self.has_rocket = False            # 没有火箭库存
        self.boost_until = 0.0             # 不在加速中
        self.food = self.spawn_food()      # 注意 spawn_food 会检查场上道具，所以道具要先置 None
        self.score = 0
        self.paused = False
        self.game_over = False
        self.saved = False                 # 本局成绩是否已保存
        # 生成 NPC；万一 500 次尝试都没找到空位（几乎不可能），先空着稍后重生
        if not self.spawn_npc():
            self.npc = []
            self.schedule_npc_respawn(self.epoch)
        self.schedule_golden(self.epoch)   # 安排第一颗金苹果
        self.schedule_rocket(self.epoch)   # 安排第一个火箭
        self.update_score_label()

    def draw_background(self):
        """画一次棋盘格背景，打上 "bg" 标签。

        之后每帧只 delete("dynamic")，背景对象完全不动——
        这比每帧重画 600 个格子省得多。这就是标签(tag)的用法：
        delete 可以按标签批量删除。
        """
        self.canvas.delete("bg")
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                color = BG_DARK if (x + y) % 2 == 0 else BG_LIGHT
                self.canvas.create_rectangle(
                    x * CELL_SIZE, y * CELL_SIZE,
                    (x + 1) * CELL_SIZE, (y + 1) * CELL_SIZE,
                    fill=color, outline="", tags="bg",
                )

    # ---------- 6.2 各种"生成" ----------

    def _free_cells(self):
        """返回当前所有空格（不在任何蛇身上、也不是任何道具的格子）。"""
        occupied = set(self.snake) | set(self.npc) | {self.food, self.golden, self.rocket}
        return [
            (x, y)
            for x in range(GRID_WIDTH)
            for y in range(GRID_HEIGHT)
            if (x, y) not in occupied
        ]

    def spawn_food(self):
        """随机找一个不在任何蛇身上、也不是其他道具的格子放普通苹果。"""
        while True:
            pos = (random.randrange(GRID_WIDTH), random.randrange(GRID_HEIGHT))
            if pos not in self.snake and pos not in self.npc \
                    and pos != self.golden and pos != self.rocket:
                return pos

    def spawn_npc(self):
        """随机生成一条长度 5~8 的 NPC 蛇。

        思路：随机选头位置 + 朝向，身体 = 从头开始沿反方向排 length 格。
        如果整条身体都在界内且不压着玩家，就成功；否则重试（最多500次）。
        """
        for _ in range(500):
            length = random.randint(5, 8)
            direction = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            hx = random.randrange(GRID_WIDTH)
            hy = random.randrange(GRID_HEIGHT)
            body = [(hx - i * direction[0], hy - i * direction[1]) for i in range(length)]
            in_bounds = all(0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT for x, y in body)
            hits_player = any(cell in self.snake for cell in body)
            if in_bounds and not hits_player:
                self.npc = body
                self.npc_direction = direction
                return True
        return False

    # ---- 定时任务：after(毫秒, 函数) 是 tkinter 的"定时器" ----
    # 注意 lambda 里捕获了 epoch：任务真正执行时会检查 epoch 是否还是当前的，
    # 如果不是（说明玩家已经按 R 重开或 ESC 退出了），就直接放弃执行。这叫"代次校验"。

    def schedule_npc_respawn(self, epoch):
        """NPC 死亡 3 秒后重生。"""
        self.after(NPC_RESPAWN_MS, lambda: self.respawn_npc(epoch))

    def respawn_npc(self, epoch):
        if epoch != self.epoch or self.game_over:
            return
        if not self.spawn_npc():           # 找不到空位就再等 3 秒
            self.npc = []
            self.schedule_npc_respawn(epoch)

    def schedule_golden(self, epoch):
        """5~10 秒后尝试生成一颗金苹果。"""
        delay = random.randint(5000, 10000)
        self.after(delay, lambda: self.spawn_golden(epoch))

    def spawn_golden(self, epoch):
        if epoch != self.epoch or self.game_over:
            return
        if self.golden is None:            # 场上最多同时存在一颗
            free = self._free_cells()
            if free:
                self.golden = random.choice(free)
        self.schedule_golden(epoch)        # 无论是否生成成功，都预约下一次尝试

    def schedule_rocket(self, epoch):
        """8~15 秒后尝试生成一个火箭。"""
        delay = random.randint(ROCKET_SPAWN_MIN, ROCKET_SPAWN_MAX)
        self.after(delay, lambda: self.spawn_rocket(epoch))

    def spawn_rocket(self, epoch):
        if epoch != self.epoch or self.game_over:
            return
        if self.rocket is None:            # 场上最多同时存在一个
            free = self._free_cells()
            if free:
                self.rocket = random.choice(free)
        self.schedule_rocket(epoch)

    # ---------- 6.3 键盘输入 ----------

    def on_key_press(self, event):
        key = event.keysym  # tkinter 给每个键起的名字
        directions = {
            "Up": (0, -1),
            "Down": (0, 1),
            "Left": (-1, 0),
            "Right": (1, 0),
        }
        if key in directions:
            new_dir = directions[key]
            # 禁止 180° 掉头：新方向与当前方向相加为 (0,0) 说明正好相反
            if (new_dir[0] + self.direction[0], new_dir[1] + self.direction[1]) != (0, 0):
                self.pending_direction = new_dir
            # 注意：只改"待生效方向"，本帧方向不变——防止一帧内连续按两键穿身
        elif key == "space" and not self.game_over:
            self.paused = not self.paused  # 空格 = 暂停开关（布尔值取反）
            self.update_score_label()
        elif key.lower() == "q":
            # 使用火箭：手里有货且当前不在加速中，才点燃
            if self.has_rocket and time.time() >= self.boost_until:
                self.has_rocket = False
                self.boost_until = time.time() + BOOST_DURATION  # 记录加速截止时刻
                self.update_score_label()
        elif key.lower() == "r" and self.game_over:
            self.start_game()

    # ---------- 6.4 游戏循环与核心逻辑 ----------

    def game_loop(self):
        """游戏循环：正常情况下每 GAME_SPEED 毫秒执行一次。

        after 不是递归调用，而是"向 tkinter 事件队列注册一个延时任务"，
        由 tkinter 主循环(mainloop)到时回调——这是 GUI 程序的通用节奏器。

        加速中：把间隔除以 BOOST_FACTOR（速度翻倍）。
        """
        if self.app.game_active and not self.paused and not self.game_over:
            self.step()
        self.draw()
        if time.time() < self.boost_until:
            interval = GAME_SPEED // BOOST_FACTOR   # 加速：间隔减半
        else:
            interval = GAME_SPEED
        self.after(interval, self.game_loop)  # 自我续期，循环下去

    def step(self):
        """前进一帧：先移动玩家，再移动 NPC。"""
        # ---- 玩家移动 ----
        self.direction = self.pending_direction  # 本帧采用按键缓存的方向
        head_x, head_y = self.snake[0]
        new_head = (head_x + self.direction[0], head_y + self.direction[1])

        # 情况1：撞墙 —— 金苹果免疫可以免死一次，随机转向
        if not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT):
            if self.shield:
                self.use_shield_turn()
                new_head = (head_x + self.direction[0], head_y + self.direction[1])
            else:
                self.end_game()
                return

        # 情况2：撞到 NPC —— 金苹果免疫同样可以免死一次，随机转向
        if new_head in self.npc:
            if self.shield:
                self.use_shield_turn()
                new_head = (head_x + self.direction[0], head_y + self.direction[1])
            else:
                self.end_game()
                return

        # 情况3：撞到自己 —— 免疫管不了自己，直接阵亡
        if new_head in self.snake:
            self.end_game()
            return

        # 把新头插到列表最前面 = 前进一格
        self.snake.insert(0, new_head)

        # 吃到普通苹果：加分、重新生成食物、身体变长（不弹尾巴）
        if new_head == self.food:
            self.score += 10
            self.food = self.spawn_food()
        # 吃到金苹果：获得/刷新免疫（生效中再吃不叠加）
        elif new_head == self.golden:
            self.golden = None
            if not self.shield:
                self.shield = True
            self.update_score_label()
        # 捡到火箭：放入库存（手里已有一个就不再叠加），按 Q 使用
        elif new_head == self.rocket:
            self.rocket = None
            if not self.has_rocket:
                self.has_rocket = True
            self.update_score_label()
        else:
            self.snake.pop()  # 没吃到东西就弹掉尾巴 = 长度不变地前进

        # ---- NPC 移动（玩家走完才走） ----
        self.step_npc()

    def use_shield_turn(self):
        """消耗金苹果免疫：随机换方向继续活（优先选安全方向）。"""
        self.shield = False
        self.direction = self.pending_direction = self.random_turn()
        self.update_score_label()

    def random_turn(self):
        """金苹果触发时随机换方向：优先安全（不撞墙不撞蛇），其次只看墙，绝不掉头。"""
        head_x, head_y = self.snake[0]
        all_dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        # 排除掉头方向：新方向 + 当前方向 == (0,0) 即为掉头
        candidates = [
            d for d in all_dirs
            if (d[0] + self.direction[0], d[1] + self.direction[1]) != (0, 0)
        ]
        # 第一层筛选：不出界的
        in_bounds = [
            d for d in candidates
            if 0 <= head_x + d[0] < GRID_WIDTH and 0 <= head_y + d[1] < GRID_HEIGHT
        ]
        # 第二层筛选：在界内且不撞任何蛇的
        safe = [
            d for d in in_bounds
            if (head_x + d[0], head_y + d[1]) not in self.snake
            and (head_x + d[0], head_y + d[1]) not in self.npc
        ]
        if safe:
            return random.choice(safe)
        if in_bounds:
            return random.choice(in_bounds)
        return random.choice(candidates)  # 四面楚歌也要选一个（下一步可能阵亡）

    def step_npc(self):
        """NPC 前进一帧，规则与玩家对称。"""
        if not self.npc:  # NPC 已死亡等待重生时跳过
            return

        self.npc_direction = self.choose_npc_direction()
        hx, hy = self.npc[0]
        new_head = (hx + self.npc_direction[0], hy + self.npc_direction[1])

        # 撞墙或撞到自己 → NPC 死亡（自杀不给玩家奖励）
        if (
            not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT)
            or new_head in self.npc
        ):
            self.npc = []
            self.schedule_npc_respawn(self.epoch)
            return

        self.npc.insert(0, new_head)

        # NPC 的头碰到玩家身体 → 被击杀，玩家 +1000
        if new_head in self.snake:
            self.npc = []
            self.score += 1000
            self.update_score_label()
            self.schedule_npc_respawn(self.epoch)
            return

        # 吃到普通苹果会变长（金苹果、火箭只对玩家有效）
        if new_head == self.food:
            self.food = self.spawn_food()
        else:
            self.npc.pop()

    def choose_npc_direction(self):
        """NPC 的"AI"：每一步怎么选方向。

        策略：
          1. 永不掉头（蛇类通用规则）。
          2. 边界和自己的身体必躲。
          3. 玩家的身体 80% 概率躲、20% 概率无视（可能撞上来送击杀）。
          4. 在安全的方向里，优先选离苹果最近的（多个并列就随机挑）。
          5. 一个安全方向都没有（走投无路）→ 随机走，听天由命。
        """
        head = self.npc[0]
        cur = self.npc_direction
        all_dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        candidates = [
            d for d in all_dirs
            if (d[0] + cur[0], d[1] + cur[1]) != (0, 0)
        ]

        # 危险格集合：自己的身体（尾尖马上要移走，所以算到 npc[:-1]）
        danger = set(self.npc[:-1])
        # 关键改动：只有 80% 的概率把玩家身体也算进危险格
        if random.random() < 0.8:
            danger |= set(self.snake)

        # 筛出"出界或踩危险格"以外的安全方向
        safe = []
        for d in candidates:
            nx, ny = head[0] + d[0], head[1] + d[1]
            if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT and (nx, ny) not in danger:
                safe.append(d)

        if not safe:  # 走投无路
            return random.choice(candidates)

        # 曼哈顿距离：|x差|+|y差|，用来比"谁离苹果更近"
        fx, fy = self.food

        def dist(d):
            return abs(head[0] + d[0] - fx) + abs(head[1] + d[1] - fy)

        best = min(dist(d) for d in safe)
        return random.choice([d for d in safe if dist(d) == best])

    # ---------- 6.5 游戏结束与成绩保存 ----------

    def end_game(self):
        self.game_over = True
        self.show_game_over_ui()

    def show_game_over_ui(self):
        """在画布上嵌入输入框和按钮（create_window 可以把控件放进画布）。"""
        cx = GRID_WIDTH * CELL_SIZE / 2
        cy = GRID_HEIGHT * CELL_SIZE / 2

        entry = tk.Entry(self.canvas, font=("Microsoft YaHei", 12), justify="center")
        entry.insert(0, "匿名玩家")  # 预填默认值，用户可直接回车
        entry.bind("<Return>", lambda e: self.save_score())  # 回车 = 保存
        win1 = self.canvas.create_window(cx, cy + 42, window=entry)

        btn = make_button(self.canvas, "保存成绩", self.save_score, width=12)
        win2 = self.canvas.create_window(cx, cy + 76, window=btn)

        text_id = self.canvas.create_text(
            cx, cy + 104, text="输入用户名后点击保存（或按回车）",
            fill="#a5d6a7", font=("Microsoft YaHei", 10), tags="dynamic",
        )
        # 把这些临时控件和画布对象记下来，重开/保存后要统一清理
        self.game_over_ui = [entry, btn, win1, win2, text_id]

    def save_score(self):
        if self.saved:  # 防止重复保存刷榜
            return
        entry = self.game_over_ui[0]
        name = entry.get().strip() or "匿名玩家"
        self.app.save_score_record(name, self.score)
        self.saved = True
        self.clear_game_over_ui()
        # 保存后换一行提示文字
        cx = GRID_WIDTH * CELL_SIZE / 2
        cy = GRID_HEIGHT * CELL_SIZE / 2
        text_id = self.canvas.create_text(
            cx, cy + 42, text=f"已保存成绩：{name}  {self.score} 分",
            fill="#7CFC00", font=("Microsoft YaHei", 12, "bold"), tags="dynamic",
        )
        self.game_over_ui = [text_id]

    def clear_game_over_ui(self):
        """销毁游戏结束时创建的临时控件。

        分两类处理：画布对象（int）用 canvas.delete，
        真实控件（Entry/Button）必须先 destroy 释放资源。
        """
        for item in self.game_over_ui:
            if isinstance(item, int):
                self.canvas.delete(item)
        for item in self.game_over_ui:
            if not isinstance(item, int):
                item.destroy()
        self.game_over_ui = []

    # ---------- 6.6 绘制 ----------

    def draw(self):
        """把当前游戏状态画到画布上。每帧调用。

        注意只删 "dynamic" 标签的对象，背景("bg"标签)不受影响。
        """
        self.canvas.delete("dynamic")

        if self.golden:
            self.draw_apple(*self.golden, golden=True)  # *位置 解包成两个参数
        if self.food:
            self.draw_apple(*self.food)
        if self.rocket:
            self.draw_rocket(*self.rocket)
        self.draw_snake(self.npc, "gold", "orange", self.npc_direction)
        self.draw_snake(self.snake, "#66bb6a", "#43a047", self.direction)

        # 暂停 / 结束的遮罩文字
        if self.app.game_active and self.paused:
            self.draw_center_text("已暂停", "按空格键继续")
        elif self.app.game_active and self.game_over:
            if self.saved:
                self.draw_center_text("游戏结束", f"得分: {self.score}   按 R 键重新开始")
            else:
                self.draw_center_text("游戏结束", f"得分: {self.score}   按 R 键直接重开")

    def draw_snake(self, body, head_color, body_color, direction):
        """画一条蛇：一串圆 + 带朝向的眼睛。

        body       —— 格子坐标列表，[0] 为头
        direction  —— 头的朝向，用来把眼睛画在正确的一侧
        """
        if not body:
            return
        pad = 1
        for i, (x, y) in enumerate(body):
            color = head_color if i == 0 else body_color  # 头亮色、身体暗色
            self.canvas.create_oval(
                x * CELL_SIZE + pad, y * CELL_SIZE + pad,
                (x + 1) * CELL_SIZE - pad, (y + 1) * CELL_SIZE - pad,
                fill=color, outline="", tags="dynamic",
            )
        # ---- 画眼睛 ----
        # 计算头部中心像素坐标
        hx, hy = body[0]
        cx, cy = hx * CELL_SIZE + CELL_SIZE / 2, hy * CELL_SIZE + CELL_SIZE / 2
        dx, dy = direction
        ex, ey = cx + dx * 3.5, cy + dy * 3.5   # 眼睛整体向行进方向偏移
        px, py = -dy, dx                         # 垂直于方向的单位向量（用来分左右眼）
        for s in (-1, 1):                        # s=-1 左眼、s=1 右眼
            ox, oy = ex + px * 4 * s, ey + py * 4 * s
            self.canvas.create_oval(ox - 3, oy - 3, ox + 3, oy + 3,
                                    fill="white", outline="", tags="dynamic")
            self.canvas.create_oval(ox - 1.2, oy - 1.2, ox + 1.2, oy + 1.2,
                                    fill="black", outline="", tags="dynamic")

    def draw_apple(self, x, y, golden=False):
        """画一个苹果：果身圆 + 果柄线 + 叶子小圆。

        golden=True 时画金苹果：金黄色 + 外圈光晕。
        (x0, y0) 和 (x1, y1) 是果身椭圆的左上角/右下角像素坐标。
        """
        x0, y0 = x * CELL_SIZE + 2, y * CELL_SIZE + 3
        x1, y1 = (x + 1) * CELL_SIZE - 2, (y + 1) * CELL_SIZE - 1
        if golden:
            self.canvas.create_oval(x0 - 2, y0 - 2, x1 + 2, y1 + 2,
                                    outline="#fff59d", width=2, tags="dynamic")
        self.canvas.create_oval(
            x0, y0 + 2, x1, y1,
            fill="#ffd700" if golden else "#e0342f",
            outline="#fff176" if golden else "#ff8a80",
            width=1, tags="dynamic",
        )
        sx = (x0 + x1) / 2  # 果柄画在果身上方正中间
        self.canvas.create_line(sx, y0 + 3, sx + 1, y0 - 3,
                                fill="#7a4a21", width=2, tags="dynamic")
        self.canvas.create_oval(sx, y0 - 4, sx + 8, y0 + 1,
                                fill="#3fa34d", outline="", tags="dynamic")

    def draw_rocket(self, x, y):
        """画一个小火箭：机头 + 机身 + 尾翼 + 火焰（全部用多边形拼）。"""
        x0, y0 = x * CELL_SIZE, y * CELL_SIZE
        cx = x0 + CELL_SIZE / 2
        # 机身（白色长三角）
        self.canvas.create_polygon(
            cx, y0 + 8, x0 + 5, y0 + 13, x0 + CELL_SIZE - 5, y0 + 13,
            fill="#e0e0e0", outline="", tags="dynamic",
        )
        # 机头（红色小三角，朝上表示待发射）
        self.canvas.create_polygon(
            cx, y0 + 1, x0 + 6, y0 + 8, x0 + CELL_SIZE - 6, y0 + 8,
            fill="#e53935", outline="", tags="dynamic",
        )
        # 左右尾翼（红色）
        self.canvas.create_polygon(
            x0 + 3, y0 + 11, x0 + 7, y0 + 17, x0 + 7, y0 + 11,
            fill="#e53935", outline="", tags="dynamic",
        )
        self.canvas.create_polygon(
            x0 + CELL_SIZE - 3, y0 + 11, x0 + CELL_SIZE - 7, y0 + 17,
            x0 + CELL_SIZE - 7, y0 + 11,
            fill="#e53935", outline="", tags="dynamic",
        )
        # 火焰（橙色小三角，朝下）
        self.canvas.create_polygon(
            cx, y0 + CELL_SIZE - 1, x0 + 7, y0 + 14, x0 + CELL_SIZE - 7, y0 + 14,
            fill="#ffb300", outline="", tags="dynamic",
        )

    def draw_center_text(self, line1, line2):
        """在屏幕中央画两行文字（暂停/游戏结束提示）。"""
        cx = GRID_WIDTH * CELL_SIZE / 2
        cy = GRID_HEIGHT * CELL_SIZE / 2
        self.canvas.create_text(
            cx, cy - 25, text=line1, fill="white",
            font=("Microsoft YaHei", 28, "bold"), tags="dynamic",
        )
        self.canvas.create_text(
            cx, cy + 5, text=line2, fill="white",
            font=("Microsoft YaHei", 13), tags="dynamic",
        )

    def update_score_label(self):
        """刷新底部状态栏文字。"""
        status = "（已暂停）" if self.paused else ""
        shield = "  |  金苹果免疫：就绪" if self.shield else ""
        if time.time() < self.boost_until:
            rocket = "  |  火箭加速中！"
        elif self.has_rocket:
            rocket = "  |  火箭：已拾取（按Q使用）"
        else:
            rocket = ""
        self.score_label.config(
            text=f"得分: {self.score}  |  方向键移动 空格暂停 Q火箭 击杀NPC+1000"
                 f"{shield}{rocket}{status}"
        )


# ==================== 程序入口 ====================
# 标准写法：只有直接运行本文件时（而不是被别的文件 import 时）才启动游戏
if __name__ == "__main__":
    root = tk.Tk()            # 创建根窗口（整个 GUI 的基础）
    app = PysnakeApp(root)    # 创建总控制器
    root.mainloop()           # 进入 tkinter 事件循环，程序在这里"停住"等待事件

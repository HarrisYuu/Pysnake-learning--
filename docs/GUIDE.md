# Pysnake 源码导读

> 本文档带你逐模块读懂 Pysnake 的源码。建议**先玩几局游戏**，再对照本文读代码——知道"程序要做什么"之后，"代码怎么做的"会好理解得多。

## 目录

1. [全局视角：程序架构](#一全局视角程序架构)
2. [Python 版精读（game.py）](#二python-版精读gamepy)
3. [网页版对照（pysnake.html）](#三网页版对照pysnakehtml)
4. [常见坑与调试技巧](#四常见坑与调试技巧)
5. [动手练习建议](#五动手练习建议)

---

## 一、全局视角：程序架构

```
Pysnake
├── 界面层    标题界面 / 游戏界面 / 排行榜界面（三者互相切换，任意时刻只显示一个）
├── 逻辑层    游戏循环 → 每帧执行：移动玩家 → 移动 NPC → 检查碰撞 → 吃道具
├── 数据层    游戏状态变量（蛇的位置、分数、道具）+ 排行榜（json / localStorage）
└── 表现层    把数据层的状态画到屏幕上（canvas）
```

记住一个核心思想：**游戏程序 = 一个不断重复循环的"状态更新器"**。所谓"玩"，就是用户通过按键改变状态（方向），循环负责让状态随时间演化（移动、碰撞）。

```
        ┌──────────────────────────────┐
        │  读取输入（方向键 / Q / 空格） │
        └──────────────┬───────────────┘
                       ▼
        ┌──────────────────────────────┐
 循环 → │  更新状态（移动、碰撞、吃道具） │ → 绘制 → 循环
        └──────────────────────────────┘
```

---

## 二、Python 版精读（game.py）

按文件中的注释编号 1~6 阅读，这里给出每块的设计意图。

### 1. 常量区（文件开头）

```python
CELL_SIZE = 20
GRID_WIDTH = 30
```

**为什么把数字提成常量？** 因为"30"出现在代码里时，你不知道它指格数还是分数；而 `GRID_WIDTH` 自解释。想调难度（比如加速），只改 `GAME_SPEED` 一处。

### 2. 工具函数

- `load_scores()` / `save_scores_to_file()`：典型的"读时容错"模式——文件不存在、内容损坏都返回空列表而不是崩溃。这是所有需要读外部数据的程序都应该有的防御。
- `make_button()`：**工厂函数**，把重复的配置收拢到一处。注意 `command=command` 传的是函数本身，不是 `command()`。

### 3. PysnakeApp —— 界面切换的原理

```python
for frame in (self.title_screen, self.game_screen, self.score_screen):
    frame.grid(row=0, column=0, sticky="nsew")
```

三个 `Frame` 用 `grid()` 叠在同一个格子，`tkraise()` 谁，谁就显示——相当于浏览器里给三个 `<div>` 切换 `display` 属性。这个"堆叠 + 置顶"的思路在 tkinter、CSS、Flutter 等界面框架里到处都有。

**按键分发**：所有按键绑定在根窗口，先判断 `game_active` 再决定要不要交给游戏处理——一个最简版的"路由"。

### 4. GameScreen —— 游戏状态的"真相中心"

读游戏代码先找**状态变量**（成员变量），因为循环里所有的判断、绘制都围绕它们：

| 变量 | 类型 | 含义 |
|---|---|---|
| `snake` | list[(x,y)] | 玩家蛇，`[0]` 永远是头 |
| `npc` | list[(x,y)] | NPC 蛇；**空列表 = 已死亡** |
| `direction` / `pending_direction` | (dx,dy) | 当前方向 / 按键缓存的方向 |
| `food` / `golden` / `rocket` | (x,y) 或 None | 三种道具位置 |
| `shield` / `hasRocket` | bool | 免疫是否就绪 / 是否有火箭库存 |
| `boost_until` | float(时间戳) | 加速截止时刻 |
| `epoch` | int | 时代编号（见下文） |

**为什么 direction 之外还要 pending_direction？**
如果一帧内连按"上→左"，蛇头还没动方向就变了，会出现"朝自己身体里拐"的穿身 bug。把按键先存进 `pending_direction`，下一步移动时才生效，就永远不会在本帧内掉头。

**为什么 __init__ 里要给一堆默认值？**
`game_loop()` 在构造时就启动了，而 `start_game()` 要等点击 START 才执行。第一帧 `draw()` 会访问 `self.golden` 等变量——不给默认值就是 `AttributeError`。这是本项目真实踩过的坑。

### 5. 游戏循环与碰撞判定

```python
def game_loop(self):
    if not self.paused and not self.game_over:
        self.step()
    self.draw()
    self.root.after(游戏间隔, self.game_loop)  # 自我续期
```

`after(毫秒, 函数)` 的意思是"**多少毫秒后帮我把这个函数放进事件队列**"。函数末尾再注册一次自己，就形成了循环。注意它不是递归——调用栈不会变深，事件由 tkinter 主循环统一调度。

**碰撞判定的顺序**（step 方法里）是有讲究的：

```
1. 撞墙？  ──有免疫→消耗并随机转向──┐
2. 撞NPC？ ──有免疫→消耗并随机转向──┤→ 用转向后的新头继续判断
3. 撞自己？──→ 直接阵亡（免疫无效）  │
4. 都没事 → 前进、检查吃到什么      ◄┘
```

先判墙再判 NPC 再判自己：因为金苹果转向之后可能撞上别的东西，必须拿转向后的新坐标再过一遍所有检查。

### 6. NPC AI：一个"胆小又贪吃的机器人"

`choose_npc_direction()` 是全场最值得精读的方法，它就是一个**决策流水线**：

```python
# 第1步：候选 = 四个方向 - 掉头方向
candidates = [d for d in all_dirs if d + cur != (0,0)]
# 第2步：建一张"危险格地图"
danger = set(自己的身体)
if random() < 0.8:            # 80% 概率怕玩家，20% 假装没看见
    danger |= set(玩家的身体)
# 第3步：筛掉出界和踩危险格的方向
safe = [不越界且不踩danger的d]
# 第4步：走投无路就随机；否则挑离苹果最近的（并列随机）
```

这套"候选 → 过滤 → 打分 → 选择"的流水线，是游戏 AI、推荐系统、搜索引擎的通用骨架，学会了可以迁移到任何"从若干选项里挑一个"的场景。

### 7. epoch 代次校验：一个优雅的小技巧

问题：NPC 死亡后安排了"3 秒后重生"，但玩家可能在 1 秒时按 R 重开了新局——旧任务执行时会污染新局。

解法不是去"取消"任务（tkinter 的 `after_cancel` 要保存每个任务 id，很麻烦），而是给每局发一个编号：

```python
self.epoch += 1                      # 重开时时代 +1
self.root.after(3000, lambda: self.respawn_npc(epoch))  # lambda 把当前时代"拍快照"

def respawn_npc(self, epoch):
    if epoch != self.epoch: return   # 时代对不上 → 我是旧时代的任务，作废
```

这就是**闭包捕获 + 版本号失效**的思想，在缓存、事务、消息队列里到处都是。

### 8. 绘制：标签与离屏画布

```python
self.canvas.delete("dynamic")   # 每帧只删动态对象
```

背景 600 个格子只画一次（带 `"bg"` 标签），每帧重画的只有蛇和道具。网页版同理，用了一张离屏画布整体贴图。**"静态的东西不重复画"是游戏渲染的第一课。**

### 9. 排行榜持久化

内存列表 → 排序 → `json.dump` 写文件。网页版是同一个思路，只是存储介质从文件换成了 `localStorage`。注意 `ensure_ascii=False`，否则中文用户名会变成 `\uXXXX` 转义码。

---

## 三、网页版对照（pysnake.html）

网页版故意写得和 Python 版**结构平行**，适合对照阅读：

| 概念 | Python (game.py) | 网页 (pysnake.html) |
|---|---|---|
| 游戏循环 | `root.after(ms, fn)` | `setTimeout(fn, ms)` |
| 定时任务失效 | epoch 校验 | epoch 校验（同款） |
| 界面切换 | `tkraise()` 叠 Frame | 切 div 的 `.active` class |
| 画布绘图 | `tk.Canvas` 对象 | `<canvas>` 2D 上下文 |
| 批量删除 | `canvas.delete("dynamic")` | 整体重绘（背景走离屏画布贴图） |
| 嵌入输入框 | `canvas.create_window` | 绝对定位的遮罩 div（更简单） |
| 本地存档 | `json` 文件 | `localStorage` |
| 确认弹窗 | `messagebox.askyesno` | `confirm()` |

对照时重点看两处**长得几乎一样**的代码：`chooseNpcDirection()` 和 `step()`——语言换了，逻辑一行不差，这是理解"算法与语言无关"的最好材料。

---

## 四、常见坑与调试技巧

本项目踩过/防过的坑，每个都值得记住：

1. **AttributeError：变量还没出生就被使用**
   → 循环/回调里用到的变量，必须在启动循环前给默认值。
2. **打字触发游戏按键**（输名字按 r 导致重开）
   → 分发按键前检查事件来源（`isinstance(event.widget, tk.Entry)` / `e.target.tagName`）。
3. **重开局被旧定时任务污染**
   → epoch 代次校验，别去挨个取消任务。
4. **innerHTML 覆盖后控件永久丢失**（网页版）
   → 备份原始内容，用的时候先恢复再重新绑定事件。
5. **方向键滚动页面**（网页版）
   → 游戏按键处理里 `e.preventDefault()`。

**调试方法**：Python 版在可疑处加 `print()`；网页版按 F12 打开 Console，用 `console.log()`，报错也会直接显示在红色文字里。

---

## 五、动手练习建议

按难度从浅到深，每题都是改几处代码就能完成：

- ⭐ 改 `GAME_SPEED` / `GRID_WIDTH`，体会"常量集中管理"的好处
- ⭐ 把击杀奖励从 1000 改成 500，顺便改状态栏文字
- ⭐⭐ 给金苹果加一个**倒计时显示**（提示还剩几格就要消失）
- ⭐⭐ 让 NPC 也吃金苹果获得免疫
- ⭐⭐ 增加"减速蘑菇"道具：捡到后 3 秒速度减半（照抄火箭的实现改符号）
- ⭐⭐⭐ 把 NPC 的"离苹果最近"贪心改成"绕开玩家包抄"
- ⭐⭐⭐ 给网页版加 `requestAnimationFrame` 平滑移动（格间插值）

改完记得同步两个版本——这也是体会"双实现"价值的最好方式。

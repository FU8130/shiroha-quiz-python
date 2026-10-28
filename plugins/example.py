PLUGIN_API = 1

# -*- coding: utf-8 -*-
"""示例插件：在菜单上加一项「今日提示」。

复制这个文件改名，改掉 KEY / LABEL / handler 就是一个新功能。
"""

KEY = "p"
LABEL = "今日提示"


def register(app, menu):
    def handler():
        tips = []
        if app.wrong_book:
            fresh = [q for q in app.questions
                     if q.id in app.wrong_book and app.wrong_status.get(q.id, "未掌握") == "未掌握"]
            if fresh:
                tips.append(f"还有 {len(fresh)} 道未掌握错题，去 4 → 2 练一遍")
        if not app.questions:
            tips.append("还没导入题库：按 1 选文件，或按 s 用内置示例")
        if not tips:
            tips.append("状态不错，保持每天 20 题 + 一次错题回顾")
        print()
        for tip in tips:
            print(f"  · {tip}")
        print()
        input("按回车返回...")

    menu.add(KEY, LABEL, handler)

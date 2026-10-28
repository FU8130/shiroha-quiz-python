import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
# extreme_test.py
import time
import sys
from quiz_parser.quiz_parser import QuizImportParser
from quiz_parser.models import QuestionType

def run_test(name, text, exp_q_count, assertions):
    print(f"🧪 {name} ...", end="", flush=True)
    start_time = time.time()
    try:
        res = QuizImportParser.parse_standard_text(text)
        elapsed = (time.time() - start_time) * 1000
        
        if len(res.questions) != exp_q_count:
            print(f" ❌ 失败 (题量不对: 期望 {exp_q_count}, 实际 {len(res.questions)})")
            return False
            
        if assertions:
            ok, msg = assertions(res.questions)
            if not ok:
                print(f" ❌ 失败 ({msg})")
                return False
                
        print(f" ✅ 通过 ({elapsed:.1f}ms)")
        return True
    except Exception as e:
        print(f" ❌ 崩溃 ({e})")
        return False

def main():
    print("🔥 开始进行全方位质量保证测试 (工业级 9 大场景)\n")
    success = 0
    total = 0

    print("🟢 [真实带表头英文 CSV]")
    total += 1
    text_real_csv = '''analysis,answer,id,optionA,optionB,optionC,optionD,title,序号
"【考点】Alpha通道概念

D正确。Alpha通道专用于存储选区灰度蒙版，与图层可见性无关。其余选项中，B误将""历史记录""功能当作通道；C混淆了图层堆栈与通道；A把RGB色彩通道错认成Alpha。三者均把通道概念张冠李戴。",D,2,保存图像色彩信息,保存图像未修改前的状态,保存图层,用来存储和建立选择范围,Alpha通道最主要的用途是().,2
"【考点】多媒体特征

D正确。多媒体核心在于把文本、图像、音频等多模态信息集成一体，并允许用户实时交互控制。A“标准化、娱乐化”误把行业应用当本质；B“动态性、丰富性”泛泛而谈，未突出集成交互；C“网络化、多样性”将网络环境误作多媒体自身属性。",D,3,"标准化,娱乐化","动态性,丰富性","网络化,多样性","集成性,交互性","下列选项描述""多媒体""的主要特点是().",3'''
    
    def check_real_csv(qs):
        if qs[0].answer != ["D"]: return False, f"第一题答案错误: {qs[0].answer}"
        if len(qs[0].options) != 4: return False, "第一题选项数量错误"
        if qs[1].answer != ["D"]: return False, f"第二题答案错误: {qs[1].answer}"
        if "多媒体" not in qs[1].question: return False, "第二题题干错乱"
        if qs[1].options[0].text != "标准化,娱乐化": return False, "第二题选项内逗号丢失"
        return True, ""
    if run_test("真实英文表头 + 复杂引号与换行", text_real_csv, 2, check_real_csv): success += 1

    print("\n💀 [地狱级无表头压测]")
    total += 1
    mock_lines = []
    for i in range(1, 101):
        if i % 10 == 0:
            mock_lines.append(f"解析:这包含逗号,而且没有引号,A,4,选项A,选项B,选项C,选项D,这是第{i}题,{i}")
        elif i % 10 == 1:
            mock_lines.append(f'"解析:这有半边引号,B,4,选项A,选项B,选项C,选项D,"这是第{i}题",{i}')
        elif i % 10 == 2:
            mock_lines.append(f'"解析:标准引号,带逗号",C,4,"A,1","B,2","C,3","D,4","题干带,逗号",{i}')
        else:
            mock_lines.append(f"解析:正常,D,4,A选项,B选项,C选项,D选项,正常题干,{i}")
    text_dirty = "\n".join(mock_lines)

    def check_dirty(qs):
        if len(qs) != 100: return False, f"发生截断！只解析出了 {len(qs)} 题"
        if qs[0].answer != ["B"]: return False, "首题答案错乱"
        if qs[9].answer != ["A"]: return False, "第10题答案错乱"
        if qs[99].answer != ["A"]: return False, "最后一题答案错乱"
        return True, ""
    if run_test("100题无表头脏数据压测", text_dirty, 100, check_dirty): success += 1

    print("\n🟤 [多空填空题]")
    total += 1
    text_blank = """1. 安全第一，（  ），（  ）。
答案：预防为主；综合治理"""
    
    def check_blank(qs):
        if len(qs[0].blankAnswers) != 2: return False, f"多空拆分错误: {qs[0].blankAnswers}"
        if qs[0].blankAnswers[0] != ["预防为主"]: return False, "第一空答案错误"
        return True, ""
    if run_test("复杂多空填空", text_blank, 1, check_blank): success += 1

    print("\n" + "="*50)
    if success == total:
        print(f"🎉 完美！所有 {total} 项测试全部通过！解析器固若金汤！")
    else:
        print(f"⚠️ 有 {total - success} 项未通过，请排查。")

if __name__ == "__main__":
    main()
# quiz_parser/validator.py
import re
from .models import Question, QuestionType, ImportWarning, WarningLevel

def validate(questions: list[Question]) -> list[ImportWarning]:
    warnings = []
    for q in questions:
        for msg in q.warnings:
            warnings.append(ImportWarning(WarningLevel.WARNING, q.number, msg))
        if not q.question:
            warnings.append(ImportWarning(WarningLevel.ERROR, q.number, "题干为空"))
            
        if q.type == QuestionType.SINGLE:
            if len(q.options) < 2: warnings.append(ImportWarning(WarningLevel.ERROR, q.number, "单选题缺少足够选项"))
            if not q.answer: warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "单选题未识别到答案"))
            if len(q.answer) > 1: warnings.append(ImportWarning(WarningLevel.ERROR, q.number, "单选题出现多个答案"))
        elif q.type == QuestionType.MULTIPLE:
            if len(q.options) < 2: warnings.append(ImportWarning(WarningLevel.ERROR, q.number, "多选题缺少足够选项"))
            if not q.answer: warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "多选题未识别到答案"))
        elif q.type == QuestionType.JUDGE:
            if len(q.options) < 2: warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "判断题缺少对/错选项"))
            if not q.answer: warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "判断题未识别到答案"))
        elif q.type in (QuestionType.BLANK, QuestionType.SHORT):
            if not q.answer and not q.blankAnswers:
                warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "主观题未识别到参考答案"))

        if re.search(r'(?:^|[\s。？！?])A\s*[^\s]{1,40}$', q.question) and any(o.key == 'B' for o in q.options) and not any(o.key == 'A' for o in q.options):
            warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "题干疑似混入A选项"))
            
        if re.search(r'【?\s*(?:答案|正确答案|参考答案)|(?:答案|正确答案|参考答案)\s*[:：]', q.question):
            warnings.append(ImportWarning(WarningLevel.WARNING, q.number, "题干残留答案标记"))
            
        for opt in q.options:
            if len(opt.text) > 240 or re.search(r'(?:【\s*(?:答案|正确答案|参考答案)|(?:^|[\s；;，,。])(?:答案|正确答案|参考答案)\s*[:：])', opt.text):
                warnings.append(ImportWarning(WarningLevel.WARNING, q.number, f"选项 {opt.key} 疑似粘连或混入答案"))
                
    return warnings

def dedupe_questions(questions: list[Question]) -> list[Question]:
    """按题干 + 选项 去重，防止误杀"""
    def normalize_text(text):
        return re.sub(r'[\s\u3000（）()【】\[\]{}。？?！!，,、：:；;\.\*]', '', str(text)).lower()
    
    seen = set()
    result = []
    for q in questions:
        # 特征 = 题干 + 所有选项文本
        opts_str = "|".join([f"{o.key}:{o.text}" for o in q.options])
        key = normalize_text(q.question) + "||" + normalize_text(opts_str)
        
        if key and key not in seen:
            seen.add(key)
            result.append(q)
    return result
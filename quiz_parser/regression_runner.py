"""回归测试运行器，对应官方 compare_regression.py + RegressionRunner.kt。"""
import json
from pathlib import Path
from .quiz_parser import QuizImportParser
from .models import QuestionType, WarningLevel

class RegressionRunner:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.manifest_file = data_dir / "manifest.json"
        self.expected_dir = data_dir / "expected"
        self.samples_dir = data_dir / "samples"

    def run(self):
        if not self.manifest_file.exists():
            print("未找到 manifest.json，跳过官方样例测试。")
            return True
            
        with open(self.manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        cases = manifest.get("cases", [])
        passed = 0
        failed = 0
        
        for case in cases:
            cid = case["id"]
            exp_file = self.expected_dir / f"{cid}.json"
            if not exp_file.exists():
                continue
                
            # 执行解析
            if case.get("mode") == "dual" or case.get("questionSample"):
                q_file = self.samples_dir / case["questionSample"]
                a_file = self.samples_dir / case["answerSample"]
                q_text = q_file.read_text(encoding="utf-8")
                a_text = a_file.read_text(encoding="utf-8")
                result = QuizImportParser.parse_dual_text(q_text, a_text)
            else:
                s_file = self.samples_dir / case["sample"]
                text = s_file.read_text(encoding="utf-8")
                result = QuizImportParser.parse_standard_text(text)
                
            # 简单比对
            with open(exp_file, "r", encoding="utf-8") as f:
                exp_data = json.load(f)
                
            expected_q_count = exp_data.get("questionCount")
            actual_q_count = len(result.questions)
            
            if expected_q_count is not None and actual_q_count != expected_q_count:
                print(f"[FAIL] {cid}: 题目数量不匹配，期望 {expected_q_count}，实际 {actual_q_count}")
                failed += 1
            else:
                print(f"[PASS] {cid}")
                passed += 1
                
        print(f"\n回归结果: 通过 {passed} / {passed + failed}")
        return failed == 0

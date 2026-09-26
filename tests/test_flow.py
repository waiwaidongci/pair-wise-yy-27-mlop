import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class CollationFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor"); self.reviewer=self.db.add_user("审阅","reviewer"); self.reviewer2=self.db.add_user("审阅二","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","异文比较",self.owner)
        self.w1=self.db.add_witness(self.work,"甲本","version"); self.w2=self.db.add_witness(self.work,"乙本","fragment","馆藏残片","中段缺页")
        self.db.grant_witness_editor(self.w2,self.editor,self.owner); self.db.grant_work_access(self.work,self.reviewer,"review",self.owner); self.db.grant_work_access(self.work,self.reviewer2,"review",self.owner)
        self.passage=self.db.add_passage(self.work,"第一节","春水东流，故人南去。",self.owner)
        self.db.align_passage(self.passage,self.w1,"春水东流，故人南去。",1,self.owner)
        self.db.align_passage(self.passage,self.w2,"春水东流，[缺页]",2,self.editor)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_multilayer_revision_snapshot_export_and_lock(self):
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        rev=self.db.update_variant(variant,"春水东流，[不可辨]人南去。","墨迹受损，不再直接补写",self.editor,1)
        self.assertEqual(2,rev)
        snap=self.db.get_snapshot(self.passage,2,self.owner)
        self.assertEqual(2,snap["layer"])
        self.db.endorse_variant(variant,self.reviewer,"认可谨慎处理")
        self.db.endorse_variant(variant,self.reviewer2,"同意此层定稿")
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual(1,exported["gap_count"])
        self.assertTrue(exported["passages"][0]["variants"][0]["notes"] == [])
        self.assertEqual({"审阅","审阅二"},{e["reviewer"] for e in exported["passages"][0]["variants"][0]["endorsements"]})
        self.db.lock_passage(self.passage,self.owner,"定稿")
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.update_variant(variant,"另一文本","无意义修改",self.editor,2)
    def test_endorsement_rules_and_invalidation(self):
        self.db.grant_work_access(self.work,self.editor,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        with self.assertRaisesRegex(DomainError,"录入人"):
            self.db.endorse_variant(variant,self.editor,"自己认可自己")
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.endorse_variant(variant,self.outsider,"越权认可")
        with self.assertRaisesRegex(DomainError,"评语"):
            self.db.endorse_variant(variant,self.reviewer,"  ")
        self.db.endorse_variant(variant,self.reviewer,"同意此层")
        with self.assertRaisesRegex(DomainError,"已认可"):
            self.db.endorse_variant(variant,self.reviewer,"重复认可")
        with self.assertRaisesRegex(DomainError,"认可"):
            self.db.lock_passage(self.passage,self.owner,"定稿")
        self.db.endorse_variant(variant,self.reviewer2,"同意，可定稿")
        self.db.update_variant(variant,"春水东流，[不可辨]人南去。","墨迹受损，不再直补",self.editor,1)
        with self.assertRaisesRegex(DomainError,"认可"):
            self.db.lock_passage(self.passage,self.owner,"定稿")
        old=self.db.get_snapshot(self.passage,1,self.owner)
        self.assertEqual({"同意此层","同意，可定稿"},{e["comment"] for e in old["endorsements"]})
        self.db.endorse_variant(variant,self.reviewer,"新层同意")
        self.db.endorse_variant(variant,self.reviewer2,"新层亦可")
        self.db.lock_passage(self.passage,self.owner,"定稿")
        snap=self.db.get_snapshot(self.passage,2,self.owner)
        self.assertEqual({"审阅","审阅二"},{e["reviewer"] for e in snap["endorsements"]})
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.endorse_variant(variant,self.reviewer,"锁定后再认可")
    def test_optimistic_lock_permission_and_mark_validation(self):
        first=self.db.create_variant(self.passage,self.w2,"补足一","理由一",self.editor,0)
        with self.assertRaisesRegex(DomainError,"版本冲突"):
            self.db.create_variant(self.passage,self.w2,"补足二","理由二",self.editor,0)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.create_variant(self.passage,self.w2,"补足三","理由三",self.reviewer,1)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.export_collation(self.work,self.outsider)
        with self.assertRaisesRegex(DomainError,"括号"):
            self.db.align_passage(self.passage,self.w1,"文本[未闭合",9,self.owner)

if __name__=="__main__": unittest.main()

import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class CollationFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor"); self.reviewer=self.db.add_user("审阅","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","异文比较",self.owner)
        self.w1=self.db.add_witness(self.work,"甲本","version"); self.w2=self.db.add_witness(self.work,"乙本","fragment","馆藏残片","中段缺页")
        self.db.grant_witness_editor(self.w2,self.editor,self.owner); self.db.grant_work_access(self.work,self.reviewer,"view",self.owner)
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
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertEqual(1,exported["gap_count"])
        self.assertTrue(exported["passages"][0]["variants"][0]["notes"] == [])
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        self.db.approve_variant(variant,self.owner,"同意当前取舍")
        self.db.approve_variant(variant,self.reviewer,"复核无误")
        self.db.lock_passage(self.passage,self.owner,"定稿")
        snap=self.db.get_snapshot(self.passage,2,self.owner)
        self.assertEqual(["负责人","审阅"],[a["reviewer_name"] for a in snap["snapshot"]["approvals"]])
        self.assertEqual("复核无误",snap["snapshot"]["approvals"][1]["comment"])
        exported=self.db.export_collation(self.work,self.reviewer)
        self.assertTrue(exported["passages"][0]["variants"][0]["endorsed"])
        self.assertEqual("同意当前取舍",exported["passages"][0]["variants"][0]["approvals"][0]["comment"])
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.update_variant(variant,"另一文本","无意义修改",self.editor,2)
    def test_endorsement_required_before_lock(self):
        second=self.db.add_user("审阅乙","reviewer")
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        self.db.grant_work_access(self.work,second,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"春水东流，故人南去。","按语义补足",self.editor,0)
        with self.assertRaisesRegex(DomainError,"认可"):
            self.db.lock_passage(self.passage,self.owner,"定稿")
        with self.assertRaisesRegex(DomainError,"审阅权限"):
            self.db.approve_variant(variant,self.outsider,"外部评语")
        self.db.grant_work_access(self.work,self.editor,"review",self.owner)
        with self.assertRaisesRegex(DomainError,"录入人"):
            self.db.approve_variant(variant,self.editor,"录入人自评")
        with self.assertRaisesRegex(DomainError,"评语"):
            self.db.approve_variant(variant,self.reviewer,"  ")
        self.db.approve_variant(variant,self.reviewer,"文从字顺")
        with self.assertRaisesRegex(DomainError,"已认可"):
            self.db.approve_variant(variant,self.reviewer,"重复认可")
        with self.assertRaisesRegex(DomainError,"认可"):
            self.db.lock_passage(self.passage,self.owner,"定稿")
        self.db.approve_variant(variant,second,"同意此层")
        self.db.lock_passage(self.passage,self.owner,"定稿")
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.approve_variant(variant,self.owner,"锁定后认可")
    def test_endorsement_voided_after_content_change(self):
        second=self.db.add_user("审阅乙","reviewer")
        self.db.grant_work_access(self.work,self.reviewer,"review",self.owner)
        self.db.grant_work_access(self.work,second,"review",self.owner)
        variant=self.db.create_variant(self.passage,self.w2,"补足文本","按语义补足",self.editor,0)
        self.db.approve_variant(variant,self.reviewer,"第一层的认可")
        self.db.approve_variant(variant,second,"第一层复核")
        self.db.update_variant(variant,"改后的文本","墨迹重勘后改写",self.editor,1)
        with self.assertRaisesRegex(DomainError,"认可"):
            self.db.lock_passage(self.passage,self.owner,"定稿")
        exported=self.db.export_collation(self.work,self.owner)
        self.assertEqual([],exported["passages"][0]["variants"][0]["approvals"])
        self.assertFalse(exported["passages"][0]["variants"][0]["endorsed"])
        snap=self.db.get_snapshot(self.passage,1,self.owner)
        self.assertEqual({"第一层的认可","第一层复核"},{a["comment"] for a in snap["snapshot"]["approvals"]})
        self.db.approve_variant(variant,self.reviewer,"第二层认可")
        self.db.approve_variant(variant,second,"第二层复核")
        self.db.lock_passage(self.passage,self.owner,"定稿")
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

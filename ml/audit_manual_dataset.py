"""Strict preflight for a manually prepared four-class YOLO classification dataset."""
from __future__ import annotations
import argparse, json
from pathlib import Path

EXTS={'.jpg','.jpeg','.png','.webp'}
CLASSES=[
 'stage_1_seed_preparation',
 'stage_2_germination',
 'stage_3_growth_development',
 'stage_4_harvesting',
]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--data',type=Path,default=Path('ml/datasets/methi/yolo_classify'))
 a=p.parse_args()
 counts={s:{c:sum(1 for f in (a.data/s/c).glob('*') if f.is_file() and f.suffix.lower() in EXTS) if (a.data/s/c).is_dir() else 0 for c in CLASSES} for s in ('train','val','test')}
 missing=[f'{s}/{c}' for s,row in counts.items() for c,n in row.items() if n==0]
 report={'data':str(a.data.resolve()),'counts':counts,'ready_for_script':not missing,'missing_class_split_folders':missing,
         'note':'This checks folder completeness only. It cannot prove labels are correct or source groups are independent.'}
 print(json.dumps(report,indent=2))
 if missing: raise SystemExit(2)
if __name__=='__main__': main()

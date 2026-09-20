"""Network-free inference artifact verifier."""
import argparse
import json
from pathlib import Path
from .replay import verify_inference_bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['verify','benchmark','baseline'])
    parser.add_argument('bundle')
    parser.add_argument('--output')
    parser.add_argument('--bootstrap',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=19)
    args=parser.parse_args()
    try:
        if args.operation=='verify':
            result=verify_inference_bundle(args.bundle)
        else:
            from .evaluation import evaluate, lexical_baseline, VERSION
            path=Path(args.bundle)
            if path.stat().st_size>16000000: raise ValueError('input too large')
            rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            if not 1<=len(rows)<=10000:raise ValueError('row bounds')
            result=evaluate(rows,bootstrap=args.bootstrap,seed=args.seed) if args.operation=='benchmark' else {
                'baseline_version':VERSION,'cases':[{'case_id':r['case_id'],
                    'labels':lexical_baseline(r['excerpt'],r['language'])} for r in rows]}
        encoded=json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False)
        if args.output:Path(args.output).write_text(encoded+'\n',encoding='utf-8')
        else:print(encoded)
    except (ValueError,OSError,KeyError,TypeError):
        parser.exit(1,'Invalid inference input or output path\n')


if __name__=='__main__': main()

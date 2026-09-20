"""Network-free inference artifact verifier."""
import argparse
import json
from .replay import verify_inference_bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['verify'])
    parser.add_argument('bundle')
    args=parser.parse_args()
    try:
        result=verify_inference_bundle(args.bundle)
    except (ValueError,OSError):
        parser.exit(1,'Invalid inference bundle\n')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__': main()

import argparse
import os
import sys
import time

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', dest='num_iters', type=int, default=5000)
    parser.add_argument('-p', dest='pause', type=float, default=0.1)
    args = parser.parse_args()

    print('num_iters=%d' % args.num_iters)
    print('pause=%f' % args.pause)

    for i in range(args.num_iters):
        print('Iteration #%05d [STDOUT] (pid=%d)' % (i, os.getpid()), file=sys.stdout)
        print('Iteration #%05d [STDERR] (pid=%d)' % (i, os.getpid()), file=sys.stderr)
        time.sleep(args.pause)

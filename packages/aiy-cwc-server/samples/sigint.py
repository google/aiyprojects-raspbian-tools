import time
import signal

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    i = 0
    while True:
        print('Tick:', i)
        i += 1
        time.sleep(1)

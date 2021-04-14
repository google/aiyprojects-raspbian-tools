import subprocess

if __name__ == '__main__':
    output = subprocess.check_output(['uname', '-a'])
    print(output.decode('UTF-8'), end='')

    output = subprocess.check_output(['cat', '/etc/aiyprojects.info'])
    print(output.decode('UTF-8'), end='')

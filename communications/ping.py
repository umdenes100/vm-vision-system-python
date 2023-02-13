import platform
import subprocess


def ping(host):
    """
    Returns True if host (str) responds to a ping request.
    Remember that a host may not respond to a ping (ICMP) request even if the host name is valid.
    """
    timeout = 3.0  # in seconds

    # Option for the number of packets as a function of
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    param2 = '-w' if platform.system().lower() == 'windows' else '-W'
    timeout = f'{timeout * 1000}' if platform.system().lower() == 'windows' else f'{timeout}'
    # Building the command. Ex: "ping -c 1 google.com"
    command = ['ping', param, '1', param2, timeout, host]

    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0
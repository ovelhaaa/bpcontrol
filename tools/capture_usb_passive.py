"""Bounded Windows USBPcap capture, filtered at source. No device commands.

Run in an elevated terminal after verifying current USBPcap device mapping.
"""
import argparse
import ctypes
import re
from pathlib import Path
import subprocess
import time


def locate_board():
    """Re-enumerate every run: USBPcap instance numbers can change on reboot."""
    exe = r'C:\Program Files\USBPcap\USBPcapCMD.exe'
    inventory = subprocess.run([exe, '--extcap-interfaces'], capture_output=True,
                               text=True, errors='replace', check=True, timeout=10).stdout
    matches = set()
    for interface in re.findall(r'value=\\\\\.\\(USBPcap\d+)', inventory):
        config = subprocess.run([exe, '--extcap-interface', '\\\\.\\' + interface,
                                 '--extcap-config'], capture_output=True, text=True,
                                errors='replace', check=True, timeout=10).stdout
        for line in config.splitlines():
            if '{display=mvsilicon B1 usb audio}' in line:
                parent = re.search(r'\{parent=(\d+)\}', line)
                if parent:
                    matches.add((interface, int(parent[1])))
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one BP1032 candidate; aborting without capture')
    return matches.pop()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface')
    p.add_argument('--device', type=int)
    p.add_argument('--seconds', type=int, default=30, choices=range(5, 61))
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    interface, device = locate_board()
    if ((args.interface is not None and args.interface != interface) or
            (args.device is not None and args.device != device)):
        p.error(f'Stale mapping: board now on {interface}, device {device}; no capture started')
    args.interface, args.device = interface, device
    if not 1 <= args.device <= 127:
        p.error('Device address must be 1..127')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        p.error('Execute in a PowerShell opened as administrator; no capture started.')
    if args.output.exists():
        p.error('Output already exists; choose a new filename')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    usb = tshark = None
    try:
        usb = subprocess.Popen([r'C:\Program Files\USBPcap\USBPcapCMD.exe',
                                '-d', '\\\\.\\' + args.interface,
                                '--devices', str(args.device), '-o', '-'],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
        tshark = subprocess.Popen([r'C:\Program Files\Wireshark\tshark.exe',
                                   '-i', '-', '-a', f'duration:{args.seconds}',
                                   '-w', str(args.output)], stdin=usb.stdout)
        usb.stdout.close()
        print(f'CAPTURE: {args.interface} address {args.device}, {args.seconds}s. Consult Guitar Chorus in ACPWorkbench now.', flush=True)
        deadline = time.monotonic() + args.seconds + 15
        while tshark.poll() is None:
            if usb.poll() is not None and usb.returncode != 0:
                raise RuntimeError('USBPcap exited before capture completed')
            if time.monotonic() >= deadline:
                raise TimeoutError('Capture watchdog expired')
            time.sleep(0.2)
        if tshark.returncode:
            raise RuntimeError(f'TShark failed: {tshark.returncode}')
    finally:
        for proc in (tshark, usb):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
    print('Capture ended; child processes released. Keep raw file local.')
    count = subprocess.run([r'C:\Program Files\Wireshark\tshark.exe', '-r',
                            str(args.output), '-T', 'fields', '-e', 'frame.number'],
                           capture_output=True, text=True, check=True, timeout=15)
    total = len(count.stdout.splitlines())
    print(f'Captured records: {total}')
    if total == 0:
        raise RuntimeError('Empty capture: no protocol evidence collected')


if __name__ == '__main__':
    main()

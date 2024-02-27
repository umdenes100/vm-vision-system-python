import logging


def reset_usb():
    import subprocess

    logging.debug('Resetting USB Devices...')

    process = subprocess.Popen(['lsusb'], stdout=subprocess.PIPE)
    out = process.communicate()[0].decode().strip().split('\n')

    ret = []
    for usb in out:
        if "Microdia" in usb or "Webcam" in usb:
            stuff = usb.split()
            process = subprocess.Popen(['sudo', 'usbreset', f'{stuff[1]}/{stuff[3]}'], stdout=subprocess.PIPE)
            out, err = process.communicate()
            if out is None:
                ret.append(err.decode("utf-8"))
            elif err is None:
                ret.append(out.decode("utf-8"))
            else:
                ret.append(f'{out.decode("utf-8")} {err.decode("utf-8")}')
    logging.debug('USB Devices Reset Complete. Starting Vision System...')

    return "".join(ret).replace('Resetting', 'reset ')

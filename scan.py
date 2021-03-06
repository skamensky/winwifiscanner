import subprocess
import re
import textwrap
import datetime
import time
import traceback
import ctypes
import os
from pathlib import Path
import sys
import argparse

os.add_dll_directory(Path(__file__).parent.absolute())

dll_name = "WlanScan32Arch.dll"
# taken from https://www.scivision.dev/python-check-32-64-bit
if sys.maxsize > 2 ** 32:
    dll_name = "WlanScan64Arch.dll"

wlan_scan = ctypes.cdll.LoadLibrary(dll_name).scan


def log_error(message):
    with open("errors.txt", "a") as file:
        file.write("-" * 10 + f"BEGIN ERROR ({format_now()})" + "-" * 10 + "\n")
        file.write(message + "\n")
        file.write("-" * 10 + "END ERROR" + "-" * 10 + "\n")


def force_wlan_rescan():
    result = wlan_scan()
    if result != 0:
        log_error(f"Problem forcing wlan scan. Error code from DLL: {result}")


def output_message(*, message, logger_level):
    if logger_level == "quiet":
        return
    print(message)
    if logger_level == "loud":
        with open("log.txt", "a") as file:
            file.write(message + "\n")


def format_now():
    return datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")


class NetworkListItem:

    # caching
    LAST_RUN = ""

    def __init__(self, *, text, logger_level):
        self.original_text = text
        self.network_type = None
        self.auth = None
        self.encryption = None
        self.bssid = None
        self.ssid = None
        self.signal_strength = 0
        self.logger_level = logger_level
        self.parse()

    def parse(self):
        base_pattern = r" {key} *: (.*)\n"
        pattern_to_attr = {
            "Network type": "network_type",
            "Authentication": "auth",
            "Encryption": "encryption",
            "BSSID 1": "bssid",
            "Signal": "signal_strength",
        }

        self.ssid = self.original_text.split("\n")[0]

        parsing_errors = []

        for pattern, attr in pattern_to_attr.items():
            formatted_pattern = base_pattern.format(key=pattern)
            search_result = re.search(formatted_pattern, self.original_text)
            groups = None
            if search_result:
                groups = search_result.groups()
            if not search_result or not groups:
                parsing_errors.append(
                    f'Ran into problem parsing {self.ssid or "one of the networks"} during the {attr} step.'
                )
                continue
            else:
                val = re.sub(r"\s", "", groups[0])
                setattr(self, attr, val)
        if parsing_errors and self.logger_level == "loud":
            message = "\n".join([e for e in parsing_errors])
            log_error(message)

        if self.signal_strength:
            self.signal_strength = int(self.signal_strength.replace("%", ""))

    def __repr__(self):
        s = self

        def item_or_not_found(item):
            return item or "netsh did not provide a value"

        return textwrap.dedent(
            f"""\
            SSID: {item_or_not_found(s.ssid)}
            BSSID: {item_or_not_found(s.bssid)}
            Signal Strength: {item_or_not_found(str(s.signal_strength)+"%")}
            Encryption: {item_or_not_found(s.encryption)}
            Network Type: {item_or_not_found(s.network_type)}
        """
        )

    @classmethod
    def parse_list(cls, *, command_output, logger_level):
        try:
            start_parsing_from = "networks currently visible."
            command_output = command_output[
                command_output.index(start_parsing_from) + len(start_parsing_from) :
            ]
            # output contains \r as well as \n. Only need one of them for newline demarcation
            command_output = re.sub(r"\r", "", command_output)
            outputs = re.split("SSID [0-9]* : ", command_output)[1:]
            return [
                NetworkListItem(text=output, logger_level=logger_level)
                for output in outputs
            ]
        except Exception:
            log_error(
                "Contents of command_output\n"
                + command_output
                + "\n"
                + "traceback\n:"
                + traceback.format_exc()
            )
            output_message(
                message="Error parsing results of netsh. Message returned: \n"
                + command_output,
                logger_level=logger_level,
            )
            return []

    def __eq__(self, other: "NetworkListItem"):
        # excludes signal strength since that varies all the time
        return (
            self.network_type == other.network_type
            and self.auth == other.auth
            and self.encryption == other.encryption
            and self.bssid == other.bssid
            and self.ssid == other.ssid
        )


class WifiOffException(Exception):
    pass


def main(logger_level, run_once=False):

    while True:

        def run():

            if logger_level == "loud":
                output_message(
                    message="Requesting a force rescan from DLL",
                    logger_level=logger_level,
                )
            force_wlan_rescan()

            cmd = "netsh wlan show networks mode=bssid"
            if logger_level == "loud":
                output_message(
                    message=f'Requesting network listing using the following command: "{cmd}"',
                    logger_level=logger_level,
                )

            command_output = subprocess.run(cmd, capture_output=True).stdout.decode()
            powered_down_msg = "The wireless local area network interface is powered down and doesn't support the requested operation."
            if powered_down_msg in command_output:
                output_message(
                    message="The wireless local area network interface is powered down. Sleeping for a bit...",
                    logger_level=logger_level,
                )
                raise WifiOffException()
            network_items = NetworkListItem.parse_list(
                command_output=command_output, logger_level=logger_level,
            )
            # sorting for the sake of the cache in NetworkListItem.LAST_RUN
            return sorted(network_items, key=lambda item: item.ssid)

        try:
            if NetworkListItem.LAST_RUN != (current_run := run()):
                NetworkListItem.LAST_RUN = current_run
                refresh_message = (
                    f"Refreshed netsh call produced new results {format_now()}" + "\n"
                )
                refresh_message += f"# of Result: {len(current_run)}" + "\n" + "-" * 20
                output_message(message=refresh_message, logger_level=logger_level)

                [
                    output_message(message=repr(item), logger_level=logger_level)
                    for item in sorted(
                        current_run, key=lambda item: item.signal_strength, reverse=True
                    )
                ]
        except WifiOffException:
            time.sleep(1)

        if run_once:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scan surrounding wifi networks on an infinite loop"
    )
    parser.add_argument(
        "-logger-level",
        dest="logger_level",
        help="The level of logging. Quiet will show no output. Default will print changed results onto the console. Loud will log every netsh result to a log.txt file and errors to an errors.txt file",
        choices=["quiet", "default", "loud"],
        default="default",
    )
    parser.add_argument(
        "-once",
        action="store_true",
        dest="run_once",
        help="Specify this flag if you want to refresh the wifi just once and do an infinite loop",
    )
    args = parser.parse_args()

    try:
        main(args.logger_level, args.run_once)
    except Exception:
        log_error(traceback.format_exc())

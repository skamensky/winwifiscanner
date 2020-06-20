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


def output_message(message, write_to_file=False):
    print(message)
    if write_to_file:
        with open("log.txt", "a") as file:
            file.write(message + "\n")


def format_now():
    return datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")


class NetworkListItem:

    # caching
    LAST_RUN = ""

    def __init__(self, *, text, verbose_error_logging):
        self.original_text = text
        self.network_type = None
        self.auth = None
        self.encryption = None
        self.bssid = None
        self.ssid = None
        self.signal_strength = 0
        self.verbose_error_logging = verbose_error_logging
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
        if parsing_errors and self.verbose_error_logging:
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
    def parse_list(cls, *, command_output, verbose_error_logging):
        try:
            start_parsing_from = "networks currently visible."
            command_output = command_output[
                command_output.index(start_parsing_from) + len(start_parsing_from) :
            ]
            # output contains \r as well as \n. Only need one of them for newline demarcation
            command_output = re.sub(r"\r", "", command_output)
            outputs = re.split("SSID [0-9]* : ", command_output)[1:]
            return [
                NetworkListItem(
                    text=output, verbose_error_logging=verbose_error_logging
                )
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
                "Error parsing results of netsh. Message returned: \n" + command_output
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


def main(verbose_logging=False):

    while True:

        def run():

            if verbose_logging:
                output_message(
                    "Requesting a force rescan from DLL", write_to_file=verbose_logging
                )
            force_wlan_rescan()

            cmd = "netsh wlan show networks mode=bssid"
            if verbose_logging:
                output_message(
                    f'Requesting network listing using the following command: "{cmd}"',
                    write_to_file=verbose_logging,
                )

            command_output = subprocess.run(cmd, capture_output=True).stdout.decode()
            powered_down_msg = "The wireless local area network interface is powered down and doesn't support the requested operation."
            if powered_down_msg in command_output:
                output_message(
                    "The wireless local area network interface is powered down. Sleeping for a bit..."
                )
                raise WifiOffException()
            network_items = NetworkListItem.parse_list(
                command_output=command_output, verbose_error_logging=verbose_logging,
            )
            return sorted(network_items, key=lambda item: item.ssid)

        try:
            if NetworkListItem.LAST_RUN != (current_run := run()):
                NetworkListItem.LAST_RUN = current_run
                refresh_message = (
                    f"Refreshed netsh call produced new results {format_now()}" + "\n"
                )
                refresh_message += f"# of Result: {len(current_run)}" + "\n" + "-" * 20
                output_message(refresh_message, write_to_file=verbose_logging)

                [
                    output_message(repr(item), write_to_file=verbose_logging)
                    for item in sorted(
                        current_run, key=lambda item: item.signal_strength, reverse=True
                    )
                ]
        except WifiOffException:
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scan surrounding wifi networks on an inifinite loop"
    )
    parser.add_argument(
        "-verbose-logging",
        action="store_true",
        dest="verbose_logging",
        help="Whether or not to write errors and each scan result to a file in the directory of the script",
    )

    args = parser.parse_args()

    try:
        main(args.verbose_logging)
    except Exception:
        log_error(traceback.format_exc())

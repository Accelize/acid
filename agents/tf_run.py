#! /usr/bin/env python3
"""Run Terraform with retries"""


def tf_run(terraform="terraform", args=None):
    """
    Run Terraform.

    Args:
        terraform (str): Terraform executable.
        args (list of str): Terraform arguments.
    """
    import sys
    import time
    import subprocess
    import json
    import pprint

    warns = set()
    retries = 10
    failures = 0
    command = [terraform] + (args or sys.argv[1:])
    with open("retries.json", "rt") as file:
        retryable_errors = json.load(file)

    while True:
        process = subprocess.run(
            command, universal_newlines=True, stderr=subprocess.PIPE, stdout=sys.stdout
        )
        if not process.returncode:
            for warn in warns:
                print(f"\033[33mWARNING: {warn}\033[30m")
            return
        elif failures > retries:
            sys.exit(f"\033[31mFailure after {failures} retries.\033[30m")

        for error_msg in retryable_errors:
            if error_msg in process.stderr:
                failures += 1
                seconds = 2 ** failures // 2
                print(
                    f"\033[31mError, retrying after {seconds}s ({failures}/{retries})"
                    f", stderr:\033[30m\n{process.stderr.strip()}"
                )
                error = retryable_errors[error_msg]
                update_tfvars = error.get("update_tfvars")
                if update_tfvars:
                    with open("terraform.tfvars.json", "rt") as json_file:
                        tfvars = json.load(json_file)
                        tfvars.update(update_tfvars)
                    with open("terraform.tfvars.json", "wt") as json_file:
                        json.dump(tfvars, json_file)
                    print("\033[32mUpdated agent parameters:\033[30m")
                    pprint.pp(tfvars)

                error_warn = error.get("warn")
                if error_warn:
                    warns.add(error_warn)

                sys.stdout.flush()
                time.sleep(seconds)
                break

        else:
            stderr = process.stderr.strip()
            if "Error running command 'ANSIBLE_" not in stderr:
                print(stderr)
            sys.exit(process.returncode)


if __name__ == "__main__":
    tf_run()

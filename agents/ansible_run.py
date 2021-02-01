#! /usr/bin/env python3
"""Run Ansible"""


def ansible_run(ansible_playbook=None, terraform="terraform"):
    """
    Run Ansible.

    Args:
        ansible_playbook (str): Ansible playbook.
        terraform (str): Terraform executable.
    """
    from json import loads, dumps
    from os import environ
    from subprocess import run, PIPE, STDOUT
    import sys

    if ansible_playbook is None:
        ansible_playbook = environ.get("ANSIBLE_PLAYBOOK", "playbook.yml")

    tf_out = {
        key: value["value"]
        for key, value in loads(
            run(
                (terraform, "output", "-json"),
                universal_newlines=True,
                stdout=PIPE,
                stderr=STDOUT,
                check=True,
            ).stdout
        ).items()
    }

    agent_env = loads(tf_out["imageDefaultEnv"])
    agent_env.update(loads(environ["AZURE_AGENT_ENV"]))
    environ.update(
        {
            "ANSIBLE_SSH_ARGS": "-o ControlMaster=auto -o ControlPersist=60s "
            "-o PreferredAuthentications=publickey",
            "ANSIBLE_PIPELINING": "True",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_SSH_RETRIES": "3",
            "ANSIBLE_FORCE_COLOR": "True",
            "ANSIBLE_NOCOLOR": "False",
            "ANSIBLE_DEPRECATION_WARNINGS": "False",
            "ANSIBLE_ACTION_WARNINGS": "False",
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "False",
            "ANSIBLE_STDOUT_CALLBACK": "debug",
            "AZURE_AGENT_ENV": dumps(agent_env),
        }
    )

    sys.exit(
        run(
            (
                "ansible-playbook",
                ansible_playbook,
                "-u",
                tf_out["user"],
                "--private-key",
                tf_out["privateKey"],
                "-i",
                f"{tf_out['ipAddress']},",
            ),
            universal_newlines=True,
        ).returncode
    )


if __name__ == "__main__":
    ansible_run()

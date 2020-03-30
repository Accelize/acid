#! /usr/bin/env python3
"""
Acid CLI entry point
"""
import sys
from os import chdir, chmod, environ, getcwd, listdir, makedirs, symlink
from os.path import dirname, expanduser, isdir, isfile, join, realpath

ACID_DIR = dirname(realpath(__file__))
AGENTS_SRC = join(ACID_DIR, "agents")
AGENTS_DIR = join(ACID_DIR, ".cache/agents")


class _Actions:
    """Available actions"""

    @staticmethod
    def _start(agent_dir, **parameters):
        """
        Start the agent.

        Args:
            agent_dir (str): Agent directory.
            **parameters: Command parameters
        """
        from json import dump
        from __init__ import (
            ensure_ansible_roles,
            get_terraform,
            call,
            TF_PLUGINS,
            dump_tfvars,
            define_unique_name,
        )

        # Initialize variables
        provider = parameters["provider"]
        agent_src = join(AGENTS_SRC, provider)
        parameters["ansiblePlaybook"] = realpath(
            expanduser(parameters["ansiblePlaybook"])
        )
        parameters["agentName"] = agent_name = define_unique_name(
            parameters["agentDescription"]
        )

        for key, parameter in (
            ("AZURE_AGENT_SHUTDOWN_TIMEOUT", "timeout"),
            ("AZURE_AGENT_NAME", "agentName"),
            ("AZURE_AGENT_POOL", "agentPool"),
            ("AZURE_AGENT_URL", "agentOrganizationUrl"),
            ("AZURE_AGENT_TOKEN", "agentManagerToken"),
        ):
            if parameters[parameter] is not None:
                environ[key] = parameters[parameter]
        del parameters["agentManagerToken"]
        environ[
            "ANSIBLE_ROLES_PATH"
        ] = f"{ACID_DIR}/.cache/lib/ansible/roles:{ACID_DIR}/roles"

        # Initialize Ansible
        _print("Initialize Ansible")
        ensure_ansible_roles(parameters["ansiblePlaybook"])

        # Initialize Terraform and agent directory
        _print("Initialize Terraform")
        terraform = get_terraform()

        makedirs(agent_dir, exist_ok=True)
        chmod(agent_dir, 0o700)

        with open(join(agent_dir, "parameters.json"), "wt") as file:
            # Save parameters
            dump(parameters, file)

        for name in listdir(agent_src):
            # Get Terraform configuration files
            if name not in (".artifactignore",):
                symlink(join(agent_src, name), join(agent_dir, name))

        tf_env = environ.copy()
        tf_env["TF_PLUGIN_CACHE_DIR"] = TF_PLUGINS
        call((terraform, "init", "-input=false"), cwd=agent_dir, env=tf_env)

        # Initialize configuration
        _print("Initialize Terraform variables")
        dump_tfvars(
            agent_dir,
            name=agent_name,
            image=parameters["image"],
            playbook=parameters["ansiblePlaybook"],
        )
        print(f"Agent resource name: {agent_name}")

        # Start Agent
        _print("Start agent")
        if provider == "awsEc2":
            dump_tfvars(
                agent_dir,
                instance_type=parameters["instanceType"],
                spot=parameters["spot"],
            )
            sys.path.append(agent_dir)
            from apply_with_spot_retries import apply

            chdir(agent_dir)
            apply(terraform=terraform)

        _print("Operation completed")

    @staticmethod
    def _stop(agent_dir, **parameters):
        """
        Stop the agent.

        Args:
            agent_dir (str): Agent directory.
            **parameters: Command parameters
        """
        if not parameters["force"]:
            confirm = ""
            while confirm != "y":
                confirm = (
                    input(
                        f"Confirm the destruction of the agent "
                        f'"{parameters["agentDescription"]}" (y/n): '
                    )
                    .strip()
                    .lower()
                )
                if confirm == "n":
                    _print("Operation cancelled")
                    return

        from __init__ import get_terraform, call, TF_PLUGINS

        parameters.update(_get_parameters(agent_dir))

        _print("Initialize Terraform plugins")
        terraform = get_terraform()
        tf_env = environ.copy()
        tf_env["TF_PLUGIN_CACHE_DIR"] = TF_PLUGINS
        call((terraform, "init", "-input=false"), cwd=agent_dir, env=tf_env)

        _print("Stop agent")
        call((terraform, "destroy", "-auto-approve", "-input=false"), cwd=agent_dir)

        from shutil import rmtree

        rmtree(agent_dir, ignore_errors=True)

        _print("Operation completed")

    @staticmethod
    def _list(*_, **__):
        """
        List agents.
        """
        print("\n".join(listdir(AGENTS_DIR)))

    @staticmethod
    def _show(agent_dir, **_):
        """
        Show the agent parameters and outputs.

        Args:
            agent_dir (str): Agent directory.
        """
        output = _get_tf_output(agent_dir, check=False)
        output["agentDirectory"] = agent_dir
        print(
            "PARAMETERS:",
            _mklist(_get_parameters(agent_dir)),
            "OUTPUTS:",
            _mklist(output),
            sep="\n",
        )

    @staticmethod
    def _ssh(agent_dir, **parameters):
        """
        SSH to the agent.

        Args:
            agent_dir (str): Agent directory.
            **parameters: Command parameters
        """
        ssh_args = parameters["ssh_args"]
        if "-i" in ssh_args:
            raise ValueError('Do no provides "-i" SSH argument, it is managed by Acid.')

        # Get connection information from Terraform
        out = _get_tf_output(agent_dir)
        cwd = getcwd()
        chdir(agent_dir)
        private_key = realpath(out["privateKey"])
        user = out["user"]
        ip_address = out["ipAddress"]

        # Run SSH
        from subprocess import run

        run(["ssh", f"{user}@{ip_address}", "-i", private_key] + ssh_args, cwd=cwd)


def _get_parameters(agent_dir):
    """
    Get the agent parameters.
    Args:
        agent_dir (str): Agent directory.
    """
    from json import load

    with open(join(agent_dir, "parameters.json"), "rb") as file:
        return load(file)


def _mklist(values):
    """
    Format a list of str.

    Args:
        values (dict): Values.

    Returns:
        str: list
    """
    return "\n".join(f"- {key}={value}" for key, value in values.items())


def _get_tf_output(agent_dir, check=True):
    """
    Get the agent Terraform output.

    Args:
        agent_dir (str): Agent directory.
    """
    from json import loads
    from __init__ import get_terraform, call

    output = call(
        (get_terraform(), "output", "-json"),
        cwd=agent_dir,
        capture_output=True,
        check=check,
    )

    if not check and output.returncode:
        return dict()

    return {key: value["value"] for key, value in loads(output.stdout).items()}


def _print(text):
    """
    Print text with color.

    Args:
        text (str): Text to print.
    """
    print(f"\033[34m{text}\033[30m")


def _run():
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(prog="acid", description="Acid CLI")
    sub_parsers = parser.add_subparsers(
        dest="parser_action", title="Commands", help="Commands", description=""
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="If True, show full error traceback."
    )
    parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="If True, Update packages, Ansible roles an other utilities.",
    )

    makedirs(AGENTS_DIR, exist_ok=True)
    chmod(AGENTS_DIR, 0o700)
    agents_exists = tuple(
        name for name in listdir(AGENTS_DIR) if isdir(join(AGENTS_DIR, name))
    )
    providers = tuple(
        name for name in listdir(AGENTS_SRC) if isdir(join(AGENTS_SRC, name))
    )

    # Defines agent loading arguments
    if len(agents_exists) == 1:
        agent_default = agents_exists[0]
    else:
        agent_default = None
    agent_load_args = dict(
        choices=agents_exists, default=agent_default, required=agent_default is None
    )

    # Start
    description = "Start a new agent."
    action = sub_parsers.add_parser(
        "start",
        help=description,
        description=description,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    action.add_argument(
        "--agentDescription",
        "-a",
        required=True,
        help="Agent description, used to identify agent in the future.",
    )
    action.add_argument(
        "--agentPool",
        "-P",
        help="Azure Pipeline Agent pool name. Can also be set with "
        '"AZURE_AGENT_POOL" environment variable.',
        default="Default",
    )
    action.add_argument(
        "--agentOrganizationUrl",
        "-o",
        help="Azure Pipeline organization URL "
        "(https://dev.azure.com/ORGANIZATION_NAME/). "
        "The agent will not be registered in Azure Pipeline if missing. "
        'Can also be set with "AZURE_AGENT_URL" environment variable.',
    )
    action.add_argument(
        "--agentManagerToken",
        "-m",
        help="Azure Personal Access Token to use to configure agent. "
        "The agent will not be registered in Azure Pipeline if missing. "
        'Can also be set with "AZURE_AGENT_TOKEN" environment variable.',
    )
    action.add_argument(
        "--provider",
        "-p",
        help="Agent instance provider.",
        default="awsEc2",
        choices=providers,
    )
    action.add_argument(
        "--instanceType", "-t", help="Agent instance type.", default="t3.nano"
    )
    action.add_argument("--image", "-i", help="Image name to use.", default="centos_7")
    action.add_argument(
        "--ansiblePlaybook",
        "-A",
        help='Path to the Ansible "playbook.yml" file used to provision the ' "agent.",
        default=(
            "playbook.yml"
            if isfile("playbook.yml")
            else join(AGENTS_SRC, "playbook.yml")
        ),
    )
    action.add_argument(
        "--timeout",
        "-T",
        help="Agent shutdown timeout in minute. "
        "If not specified, the agent will run infinitely.",
        type=int,
    )
    action.add_argument(
        "--spot",
        "-s",
        help="Use spot instance",
        type=bool,
        default=True,
        choices=(True, False),
    )

    # Stop
    description = "Stop and destroy the agent."
    action = sub_parsers.add_parser(
        "stop",
        help=description,
        description=description,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    action.add_argument(
        "--agentDescription",
        "-a",
        help="Agent description, used to select agent to stop.",
        **agent_load_args,
    )
    action.add_argument(
        "--force",
        "-f",
        help="Force agent destruction without confirmation.",
        action="store_true",
    )

    # SSH
    description = "Connect to the agent using SSH."
    action = sub_parsers.add_parser(
        "ssh",
        help=description,
        description=description,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    action.add_argument(
        "--agentDescription",
        "-a",
        help="Agent description, used to select agent to SSH.",
        **agent_load_args,
    )
    action.add_argument(
        "ssh_args", nargs="*", help='SSH command arguments (Without "-i" and "-a").'
    )

    # List
    description = "List existing agents."
    sub_parsers.add_parser(
        "list",
        help=description,
        description=description,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    # Show
    description = "Show the agent parameters."
    action = sub_parsers.add_parser(
        "show",
        help=description,
        description=description,
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    action.add_argument(
        "--agentDescription",
        "-a",
        help="Agent description, used to select agent to show.",
        **agent_load_args,
    )

    # Get action and arguments
    parameters = vars(parser.parse_args())

    parser_action = parameters.pop("parser_action")
    debug = parameters.pop("debug", False)
    update = parameters.pop("update", False)
    agent = parameters.get("agentDescription")
    try:
        agent_dir = join(AGENTS_DIR, agent)
    except TypeError:
        agent_dir = None

    if parser_action == "start":
        if isdir(agent_dir):
            parser.error(f'An agent named "{agent}" already exists, run "stop" first.')

    elif parser_action in ("stop", "ssh", "show"):
        if not isdir(agent_dir):
            parser.error(f'No agent named "{agent}", run "start" first.')

    elif parser_action not in ("list",):
        parser.error("An action is required")
        return

    try:
        # Ensure Acid can be imported
        sys.path.insert(0, ACID_DIR)

        # Enable updates
        if update:
            import __init__ as core

            core.FORCE_UPDATE = True

        # Call method
        getattr(_Actions, f"_{parser_action}")(agent_dir, **parameters)

    except KeyboardInterrupt:  # pragma: no cover
        parser.exit(status=1, message="Interrupted by user\n")

    except Exception as exception:
        if debug:
            raise
        parser.exit(status=1, message=f"\033[31m{exception}\033[30m\n")


if __name__ == "__main__":
    _run()

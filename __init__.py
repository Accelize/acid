# coding=utf-8
"""
Accelize utilities for CI/CD pipeline
"""
from os import makedirs as _makedirs
from os.path import (
    basename as _basename,
    dirname as _dirname,
    isfile as _isfile,
    join as _join,
    realpath as _realpath,
)
from sys import executable as _executable

__version__ = "1.0.0"
_CACHE = _join(_dirname(_realpath(__file__)), ".cache")
_makedirs(_CACHE, exist_ok=True)

#: Ansible roles dir
ANSIBLE_ROLES = _join(_CACHE, "lib/ansible/roles")

#: Terraform plugins dir
TF_PLUGINS = _join(_CACHE, "lib/terraform")

#: Set to True to force plugin and packages updates
FORCE_UPDATE = False


def call(command, capture_output=False, check=True, **kwargs):
    """
    Call a command with automatic error handling.

    Args:
        command (iterable of str or str):
        capture_output (bool): If True, capture stdout.
        check (bool): If True, check return code.
        kwargs: subprocess.run keyword arguments.

    Returns:
        subprocess.CompletedProcess
    """
    from subprocess import run, PIPE

    command_kwargs = dict(
        universal_newlines=True, stderr=PIPE, stdout=(PIPE if capture_output else None)
    )
    command_kwargs.update(kwargs)
    process = run(command, **command_kwargs)

    if process.returncode and check:
        if process.stderr:
            msg = f"\nStderr messages:\033[30m\n{process.stderr}"
        else:
            msg = "\033[30m"
        raise RuntimeError(f"\033[31mError code: {process.returncode}{msg}")

    return process


def ensure_pip_packages(package, import_name=None, call_name=None):
    """
    Ensure pip package is installed.

    Args:
        package (str): Package to install.
        import_name (str): Name used to import the package.
            Default to package name.
        call_name (str): Name used to executable to call.
    """
    if FORCE_UPDATE:
        call(
            (
                _executable,
                "-m",
                "pip",
                "install",
                "-U",
                "-q",
                "--disable-pip-version-check",
                package,
            )
        )
        return

    elif call_name:
        try:
            call(call_name, check=False, capture_output=True)
            return
        except FileNotFoundError:
            pass
    else:
        from importlib import import_module

        try:
            import_module(import_name or package)
            return
        except ImportError:
            pass

    call(
        (
            _executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-q",
            package,
        )
    )


def export(name, value, is_output=True):
    """
    Set a Azure pipeline variable.

    Args:
        name (str): Variable name.
        value (str): Variable value.
        is_output (bool): Make variable available to future jobs.
    """
    print(
        f"##vso[task.setvariable variable={name}"
        f'{";isOutput=true" if is_output else ""}]{value}'
    )


def render_template(src, dst, show=True, **kwargs):
    """
    Render a file from a template using Jinja2.

    Args:
        src (str): Source template.
        dst (str): Destination file.
        show (bool): If true, print result.
        kwargs: Template arguments.
    """
    ensure_pip_packages("jinja2")

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(_dirname(src)))
    template = env.get_template(_basename(src))
    rendered = template.render(**kwargs)
    if show:
        print(
            "\033[34m== START RENDERED ==\033[30m\n"
            f"{rendered}"
            "\n\033[34m== END RENDERED ==\033[30m"
        )
    with open(dst, "wt") as file:
        file.write(rendered)


def ensure_ansible_roles(path):
    """
    Ensure playbook dependencies roles are presents.

    Args:
        path (str): "playbook.yml" path.
    """
    ensure_pip_packages("ansible", call_name="ansible")
    ensure_pip_packages("pyyaml", import_name="yaml")
    try:
        from yaml import CSafeLoader as Loader
    except ImportError:
        from yaml import SafeLoader as Loader
    from yaml import load

    # Get dependencies from playbook
    try:
        with open(path, "rt") as file:
            roles = load(file, Loader=Loader)[0]["roles"]
    except KeyError:
        # No roles
        return
    dependencies = set()
    for role in roles:
        try:
            # formatted as - name: role_name
            name = role["name"]
        except KeyError:
            # Formatted as - role_name
            name = role
        if "." in name:
            dependencies.add(name)

    # Install dependencies
    if dependencies:
        _makedirs(ANSIBLE_ROLES, exist_ok=True)
        command = ["ansible-galaxy", "install", "-p", ANSIBLE_ROLES]
        if FORCE_UPDATE:
            command.append("--force-with-deps")
        call(command + list(dependencies))


def define_unique_name(project, repo="", branch="", build_id=""):
    """
    Name an unique name based on build information.

    Args:
        project (str): Project name.
        repo (str): Repository name.
        branch (str): Branch name.
        build_id (str): Build ID.

    Returns:
        str: Unique name.
    """
    from secrets import token_hex

    name = "".join(
        c
        for c in "".join(
            (
                project.capitalize(),
                repo.split("/")[-1].capitalize(),
                branch.capitalize(),
                build_id.capitalize(),
                token_hex(8),
            )
        )
        if c.isalnum()
    )

    return name


def dump_tfvars(directory, **variables):
    """
    Dump variables in "terraform.tfvars.json".
    Update existing files.

    Args:
        directory (str): Output directory.
        **variables: Variables
    """
    from json import dump, load

    path = _join(directory, "terraform.tfvars.json")

    try:
        with open(path, "rt") as json_file:
            tfvars = load(json_file)
    except FileNotFoundError:
        tfvars = dict()

    tfvars.update(variables)
    with open(path, "wt") as json_file:
        dump(tfvars, json_file)


def get_terraform():
    """
    Get utility executable path after installing or updating it.

    Returns:
        str: Terraform executable path.
    """
    dst = f"{_CACHE}/bin"
    exec_file = _join(dst, "terraform")

    # Check if executable is already installed
    if _isfile(exec_file):
        # Return directly if skip update
        if not FORCE_UPDATE:
            return exec_file

        # Get version
        for line in (
            call((exec_file, "version"), capture_output=True)
            .stdout.lower()
            .splitlines()
        ):
            if line.startswith("terraform"):
                current_version = line.split(" ")[1].strip().lstrip("v")
    else:
        current_version = None

    # Get utility release information from HashiCorp checkpoint API
    last_release = _get_terraform_version()
    last_version = last_release["current_version"]

    # If file is installed and up-to-date, returns its path
    if last_version == current_version:
        return exec_file

    # Download the latest compressed executable
    compressed = download(last_release["archive_url"])

    # Lazy import
    from os import chmod, stat
    from io import BytesIO
    from zipfile import ZipFile

    # Ensure directories exists
    _makedirs(dst, exist_ok=True)

    # Extract executable and returns its path
    compressed_file_obj = BytesIO(compressed)
    compressed_file_obj.seek(0)
    with ZipFile(compressed_file_obj) as compressed_file:
        exec_file = compressed_file.extract(compressed_file.namelist()[0], path=dst)

    # Ensure the file is executable
    chmod(exec_file, stat(exec_file).st_mode | 0o111)

    if current_version:
        print(f"\033[34mTerraform updated to {last_version}...\033[30m")
    else:
        print(f"\033[34mTerraform {last_version} installed...\033[30m")

    return exec_file


def _get_terraform_version():
    """
    Get last version information from HashiCorp checkpoint API.

    Returns:
        dict: Last version information.
    """
    # Lazy import
    from platform import machine, system
    from json import loads, load, dump
    from datetime import datetime, timedelta
    from dateutil.parser import parse

    # Configure cache
    cache = _join(TF_PLUGINS, "checkpoint.json")
    updated = False
    now = datetime.utcnow()

    # Get cached version information if available
    try:
        with open(cache, "rt") as cache_file:
            last_release = load(cache_file)
    except FileNotFoundError:
        last_release = None
    else:
        date = parse(last_release["date"])
        if date < now - timedelta(days=1):
            last_release = None

    # Update from the web
    if not last_release:
        updated = True
        last_release = loads(
            download("https://checkpoint-api.hashicorp.com/v1/check/terraform")
        )

    current_version = last_release["current_version"]
    download_url = last_release["current_download_url"].rstrip("/")

    # Define platform specific utility executable and archive name
    arch = machine().lower()
    arch = {"x86_64": "amd64"}.get(arch, arch)
    last_release[
        "archive_name"
    ] = archive_name = f"terraform_{current_version}_{system().lower()}_{arch}.zip"

    # Define download URL
    last_release["archive_url"] = f"{download_url}/{archive_name}"

    # Cache result
    if updated:
        last_release["date"] = now.isoformat()
        _makedirs(TF_PLUGINS, exist_ok=True)
        with open(cache, "wt") as cache_file:
            dump(last_release, cache_file)

    return last_release


def download(url):
    """
    Download from URL.

    Args:
        url (str): URL

    Returns:
        bytes: Response.
    """
    # Lazy import
    from urllib.request import urlopen

    with urlopen(url) as response:
        return response.read()

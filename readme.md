![Build Status](https://dev.azure.com/Accelize/DevOps/_apis/build/status/Acid?branchName=master)
[![codecov](https://codecov.io/gh/Accelize/acid-cli/branch/master/graph/badge.svg?token=TWXR4CXWS8)](https://codecov.io/gh/Accelize/acid-cli)
[![PyPI](https://img.shields.io/pypi/v/acidcli.svg)](https://pypi.org/project/acidcli)

# ACID: Accelize Continuous Integration & Delivery

This utility allows running Azure pipelines jobs on on-demand agents hosted by AWS EC2
or Azure Virtual Machine.

This allows using the Azure Pipeline self-hosted feature to run jobs on these platforms
without having to maintain (and pay) always running virtual machines in the cloud.

The agent machine is created just before the job that will require it and is stopped
once the job is completed.

The agent can be customized and configured using Ansible. Terraform is used to provision
and clean up the cloud resources.

This makes the use of hardware-specific or expensive virtual machines as Azure pipeline
agents possibles while keeping control on the cost. Spot instances are also supported
to help reduce cost.

## Azure pipeline usage

### Requirements

An agent management token needs to be configured in your Azure DevOps Project prior to
use any agent:
* In your user profile, go to "Personal Access Tokens".
* Create a new token named "agentManager", select your target "Organization",
* In "Scopes", select "Custom defined" and check "Read & manage" for "Agent Pools" and 
  "Deployment Groups".
* Click on "Create" and copy the token.
* In your Azure DevOps Project, go in "Pipelines/Library".
* In "Variable groups", create a variable group name "agentManager".
* In this group, creates a variable name "agentManagerToken" with your previously 
  created token as value.
* Change this variable type to secret.

An GitHub connection must be configured in the Azure DevOps Project:
* In your Azure DevOps Project, go in "Project Settings/Service connections".
* Click on "New service connection".
* Select "GitHub", and click "Next.
* Set "Service connection name" to "GitHub" or another name, fill your
  credentials information, and click "Save".

#### AWS EC2

The [AWS Toolkit for Azure DevOps](https://marketplace.visualstudio.com/items?itemName=AmazonWebServices.aws-vsts-tools)
must be installed on your Azure DevOps organization.

An AWS connection must be configured in the Azure DevOps Project prior to use EC2 
agents:
* In your Azure DevOps Project, go in "Project Settings/Service connections".
* Click on "New service connection".
* Select "AWS", and click "Next.
* Set "Service connection name" to "AWS" (Acid default value) or another name, fill your
  credentials information, and click "Save".

#### Azure Virtual Machines

An Azure connection must be configured in the Azure DevOps Project prior to use Azure 
virtual machine agents:
* In your Azure DevOps Project, go in "Project Settings/Service connections".
* Click on "New service connection".
* Select "Azure Resource Manager", and click "Next.
* Select "Service principal (automatic)" (or your preferred option), and click "Next.
* Set "Service connection name" to "Azure" (Acid default value) or another name, fill 
  your credentials information, and click "Save".

Some resources must be created:
* A resource group named "accelize" (Acid default value) or another name.
* A virtual network named "accelize" (Acid default value) or another name, this
  virtual network must contain at least one subnet.

### Pipeline creation

The Azure Pipeline must be a YAML pipeline.

The pipeline YAML works as normal but requires to add the following:
- The Acid repository as an extra resource.
- Jobs to start and stop the agents.
- A pool configuration on the jobs that use the created agent.

Here is a commented YAML example:
```yaml
# The Acid repository must be added as a resource to allow the use of Acid templates
resources:
  repositories:
    - repository: acid
      type: github
      name: Accelize/acid
      endpoint: GitHub  # Update with you GitHub connection name
      # Specifying a ref is not mandatory, but help to ensure to not break your
      # pipeline in case of Acid update. Acid branches names are major API versions,
      # specifying a branch is recommanded. It is also possible to specify a tag
      # to select a minor version. If nothing is specified, always uses the last 
      # version.
      ref: refs/heads/v1

jobs:

  # Agents are started using the "agents/start.yml@acid" template to create start jobs
  - template: agents/start.yml@acid
    parameters:
      # Each start job must have a unique jobName and agentDescription
      jobName: startAgent_AwsEc2_centOs8
      agentDescription: AWS EC2 CentOS 8
      # The agent can be configured with using parameters from the template
      # Read the template parameters definition for more information.
      provider: awsEc2
      image: centos_8
      instanceType: t3a.nano
  
  # Multiples agents can be started, by default in parallel
  - template: agents/start.yml@acid
    parameters:
      jobName: startAgent_AwsEc2_ubuntu1804
      agentDescription: AWS EC2 Ubuntu 18.04
      provider: awsEc2
      image: ubuntu_18_04
      instanceType: t3a.nano

  # Once the agent is started, it can be used in other jobs (Only one job a time per agent)
  - job: runTests_AwsEc2_centOs8
    displayName: Run tests on AWS EC2 CentOS 8
    # The job must depend on the "start" job that started the agent
    dependsOn: startAgent_AwsEc2_centOs8
    # The pool section must be added as following
    pool:
      # Can eventually use another pool name, but must use the same pool as defined
      # in the start job parameters (Default to "Default")
      name: Default 
      # Demand value must be as follow, the "AWS EC2 CentOS 8" is the "agentDescription"
      # from the start job
      demands:
        - agent.Name -equals $(Build.BuildId) AWS EC2 CentOS 8
    # The job steps work as normal but run on the agent you created
    steps:
      - script: pytest

  # Running tests on the second agent
  - job: runTests_AwsEc2_ubuntu1804
    displayName: Run tests on AWS EC2 Ubuntu 18.04
    dependsOn: startAgent_AwsEc2_ubuntu1804
    pool:
      name: Default
      demands:
        - agent.Name -equals $(Build.BuildId) AWS EC2 Ubuntu 18.04
    steps:
      - script: pytest

  # Once tests are completed, the agents are stopped, 
  # "agents/stop.yml@acid" template to create stop jobs
  - template: agents/stop.yml@acid
    parameters:
      # Each stop job must have a unique jobName
      jobName: stopAgent_AwsEc2_centOs8
      # Any other parameters must be identical to the start job, including 
      # "agentDescription". Some parameters are not required to be specified, read
      # the "stop.yml" template parameters definition for more information.
      provider: awsEc2
      agentDescription: AWS EC2 CentOS 8
      # The stop job must depends on the last job that used the agent, in this case our
      # tests.
      dependsOn: runTests_AwsEc2_centOs8

  # Stopping the second agent
  - template: agents/stop.yml@acid
    parameters:
      jobName: stopAgent_AwsEc2_ubuntu1804
      provider: awsEc2
      agentDescription: AWS EC2 Ubuntu 18.04
      dependsOn: runTests_AwsEc2_ubuntu1804
```

The start and stop jobs run on the Microsoft-hosted agents.

By default, agents are configured with a timeout of 60 minutes. After this timeout,
the agent instance shutdown. This timeout can be configured with the `timeout` parameter
of the start job. This timeout is set at the start of the `azure_pipeline_agent` Ansible
role. 

#### Start job configuration

Here is a description of all start job parameters.

Job configuration:
* `jobName`: Name of the start job. Any job that will use the agent must have this 
  values set in the `dependsOn` parameter. Default to `startAgent`.
* `dependsOn`: `dependsOn` value of the start job. Default to `[]`.
* `condition`: `condition` value of the start job. Default to `succeeded()`.
* `ansibleMitogen`: Set to `true` to enable 
  [Ansible Mitogen](https://mitogen.networkgenomics.com/ansible_detailed.html) to speed
  up the Ansible provisioning. Default to `false`.

Agent pool configuration:
* `agentDescription`: Short agent description. This value must be unique for all agents
  of a same pipeline. It is used to select the agent when using it in jobs (See the 
  "Agent use in other jobs" section for more information). To avoid issues, should be 
  short and use common characters. Default to `Acid`.
* `agentPool`: Name of the Azure Pipeline agent pool where to add the agent. Default to
  `Default`.
* `agentVersion`: Azure Pipeline agent version to use. Default to the latest version.

Agent hardware configuration:
* `provider`: Cloud provider to use. Possible values are `awsEc2` (AWS EC2) and 
  `azureVm` (Azure Virtual Machines). Default to `awsEc2`.
* `connection`: Name of the Azure DevOps connection to used to authenticate on the cloud
  provider. See the "Requirements" section for more information on connection
  configuration. Default values:
   * awsEc2: `AWS`
   * azureVm: `Azure`
* `region`: Region on AWS, Location on Azure. Default values:
   * awsEc2: `eu-west-1`
   * azureVm: `West Europe`
* `instanceType`: Instance type on AWS EC2, Virtual machine size on Azure Virtual 
  Machines. Default values:
   * awsEc2: `t3a.micro`
   * azureVm: `Standard_B1s`
* `volumeSize`: Root volume size in GB. Default to size specified by the image.
* `spot`: Use spot instances/virtual machines to reduce the cost with the risk of being
  de-provisioned at any time. Possibles values are `true` or `false` only. Default 
  values:
   * awsEc2: `true`
   * azureVm: `false`
* `resourceGroupName`: azureVm only. Existing resource group name to use. Default to 
  `accelize`.
* `virtualNetworkName`: azureVm only. Existing virtual network name to use. Default to 
  `accelize`.

Agent software configuration:
* `image`: OS image used on the agent. See the "OS image configuration" section for more
  information. Some images may not be supported by the Azure Pipeline agent, but are 
  provided for convenience and CLI use (See the agent documentation for more 
  information on supported OS). Default to `ubuntu_18_04`.
* `ansiblePlaybook`: Path to Ansible "playbook.yml" file, relative to 
  `Build.SourcesDirectory`. See the "Software configuration" section for more 
  information. Default to a playbook that only starts the agent.
* `ansibleRequirements`: Path to Ansible "requirements.yml" file used to define roles 
  to install, relative to `Build.SourcesDirectory`. See the "Software configuration" 
  section for more information. By default, does not install roles.
* `timeout`: Agent timeout in minutes. After this timeout, the agent will shutdown 
  itself. This is mainly intended to avoid having an instance stuck indefinitely in case
  of error. Default to `60`.
* `inMemoryWorkDir`: If `true`, the agent work directory and `/tmp` are mounted in 
  memory (tmpfs). This improves performance and security at the cost of more memory 
  usage. Default to `false`.
* `agentEnv`: Azure Pipeline agent environment variables as a JSON formatted string. 
  Can be used to pass global environment variables to the pipeline, or to pass agent 
  knobs. Default to `{}`.

#### Agent use in other jobs

Any job that will require this agent must contain the following `pool` parameter with
`agentPool` and `agentDescription` replaced by the exact values of the `agentPool` and
`agentDescription` parameters defined in the "Start job configuration" section.

```yaml
pool:
   name: agentPool
   demands:
     - agent.Name -equals $(Build.BuildId) agentDescription
```

#### Stop job configuration

Here is a description of all stop job parameters.

* `jobName`: Name of the stop job. Default to `stopAgent`.
* `dependsOn`: `dependsOn` value of the stop job. Must depend on any job that use the 
  agent. Default to `startAgent`.
* `agentDescription`: Must be the same value as the start job.
* `provider`: Must be the same value as the start job.
* `connection`: Must be the same value as the start job.
* `region`: Must be the same value as the start job.

Note: The stop job is configured to always run, even if errors on previous stages.

### Agent virtual machine configuration

#### Hardware configuration

The start job provides parameters to configure the machine that will run the agent:
Cloud provider, cloud region, instance type.

#### OS image configuration

It also provides an `image` parameter used to define the OS to use. Available OS are
a predefined list.

Acid is configured to take the latest available image matching the specification.
Names are uniformized to not depend on the cloud provider.

The following command shows available images for a provider:
```bash
acid images PROVIDER
```

##### Images configuration file

Full details on images can be found in the 
`agents/PROVIDER/images.auto.tfvars.json` file for each provider.

This file is a JSON that contain a map of images. For each image, the map key is
the image name, and the value a map of images parameters.

Some image parameters are provider dependant:

* awsEc2:
  * `name`: The AMI name. May contain the wildcard character `*`.
  * `owner`: AWS account ID or account alias of the AMI owner.
  * `user`: Username used to connect to the instance using SSH.
* azureVm:
  * `publisher`: The Publisher associated with the Platform Image.
  * `offer`: The Offer associated with the Platform Image.
  * `sku`: The SKU of the Platform Image.
  
The following generic parameters are also available:

* `agentEnv`: Default agent environment variables for this image. The global
  `agentEnv` is merged in this value. Must be a JSON formatted string.

#### Software configuration

The software installed on the agent virtual machine can be configured using Ansible.

The start job provides the `ansiblePlaybook` parameter that can be used to select
a custom Ansible Playbook to install any required software.

In case your playbook requires third party roles, you can use a  `requirements.yml` file
that need to be specified with the `ansibleRequirements` parameter.

By default, only the 
[Azure pipeline agent](https://docs.microsoft.com/en-us/azure/devops/pipelines/agents/v2-linux?view=azure-devops)
(And its dependencies) is installed.

Here is the content of the default playbook.
```yaml
---
- hosts: all
  become: true
  roles:
    - name: azure_pipeline_agent
```

The Azure pipeline agent must be installed to use the virtual machine as an agent.
Ensure the role "azure_pipeline_agent" is always present in your custom playbooks.

### Pipeline run

If Azure DevOps may authorise the use of cloud provider connection and the 
"agentManager" variable group, you must allow it and re-start the run.
This generally occurs once per pipeline on the first execution.

## Command line interface usage

Acid can also be used as a command-line utility. This feature is mainly intended to help
develop and debug in an environment identical to the one used in CI.

This utility is intended to manage one or more virtual machines that can be connected
to the Azure pipeline agent pool or not.

### Requirements

Python >= 3.6 is required.

Depending on the cloud provider you want to use, the following is also required:

#### AWS EC2

Your AWS credentials must first be installed on your machine, here is the recommended 
method:

* Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html).
* Configure your AWS credentials:
  ```bash
  aws configure
  ```

#### Azure Virtual Machines

Your Azure credentials must first be installed on your machine, here is the recommended 
method:

* Install [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli).
* Login on Azure:
  ```bash
  az login
  ```

### Installation

The installation is performed with pip:

```bash
pip3 install acidcli
```

Acid-cli support commands autocompletion using argcomplete, to enable it simply run:
```bash
activate-global-python-argcomplete --user
```

For more information on autocompletion, read the 
[argcomplete documentation](https://kislyuk.github.io/argcomplete).

### Usage

The basics commands are similar to the use of acid with YAML pipelines

The "start" command is used to start the agent end provides similar parameters than
the "start" job template:
```bash
# Minimal command with all defaults parameters
acid start --agentDescription MyAgent

# Example with more specific parameters
acid start --agentDescription MyAgent2 --provider azureVm --image centos_8 --ansiblePlaybook plabook.yaml
```

The "stop" command is used to stop agents, but, in this case, there is no need to repeat
some parameters of the "start" command like with the "stop" job

```bash
# If multiples agents exist, "--agentDescription" must be provided
acid stop --agentDescription MyAgent

# If there is only one agent, no parameters are required
acid stop
```

It is possible to connect to the agent using SSH with the following command:

```bash
acid ssh --agentDescription MyAgent

# Standard SSH command arguments are supported after "--", for instance, port forwarding
acid ssh ssh -- –L 8080:127.0.0.1:8080
```

The utility provides extra commands for convenience:
```bash
# To list agents
acid list

# To show the details on a specific agent
acid show --agentDescription MyAgent

# To show available OS images for a provider
acid images awsEc2
```

To get information about all available commands and parameters, run:
```bash
# General help
acid --help

# Command specific help, for instance, "start"
acid start --help
```

#### Environment and dependencies

The utility manages its own dependencies in an isolated Python virtual environment.

This virtual environment is created on the first "acid" call.

You can ask acid to update its dependencies with the `--update` parameter when starting
a command. Note that dependencies that are not used when running the command are not
updated.

```bash
acid start --update -a My_agent
```

Running agents information and utility dependencies (Python virtual environment,
terraform executable, downloaded Ansible roles) are stored in the `.cache` folder.

It is possible to delete this folder to fully reset the configuration. Before doing this,
ensure that all agents have been stopped first (Recommended), or do not delete the 
`.cache/agents` directory.

## Security

### Agent security

SSH ingress access is required for the Ansible configuration. Internet egress access is
required.

When an agent is created, a security group/firewall rule is created to only allow
SSH from the Microsoft-hosted agent start performs the "start" job (Or the machine that
run the `acid start` command line).

An SSH key is created at the same time and is used only once for the Ansible 
configuration. This key is stored in PEM format and in the `terraform.tfstate` file.

When using from Azure pipeline, the key is stored as artifact.
When using the command line utility the key is stored in `~/.config/acid/agents/AGENT`.

### Cloud credentials

Acid requires cloud credentials to manage agents cloud resources. This section contains
some information on how to provides minimal access to the jobs that run acid.

#### AWS

Acid requires the following IAM policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Ec2",
            "Effect": "Allow",
            "Action": [
                "sts:GetCallerIdentity",
                "ec2:DescribeAvailabilityZones",
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceAttribute",
                "ec2:DescribeSpotInstanceRequests",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeImages",
                "ec2:DescribeKeyPairs",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeVpcs",
                "ec2:DescribeVolumes",
                "ec2:DescribeAccountAttributes",
                "ec2:CreateTags",
                "ec2:ImportKeyPair",
                "ec2:RunInstances",
                "ec2:RequestSpotInstances",
                "ec2:ModifyInstanceAttribute",
                "ec2:CreateSecurityGroup",
                "ec2:AuthorizeSecurityGroupEgress",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupEgress",
                "ec2:DeleteKeyPair",
                "ec2:DeleteSecurityGroup",
                "ec2:TerminateInstances",
                "ec2:CancelSpotInstanceRequests"
            ],
            "Resource": "*"
        }
    ]
}
```

Acid deploys agents instance in the default VPC.

#### Azure

Acid requires the following permissions:
```json
[
    "Microsoft.Authorization/*/read",
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Resources/deployments/*",
    "Microsoft.Compute/*/read",
    "Microsoft.Compute/virtualMachines/*",
    "Microsoft.Compute/disks/write",
    "Microsoft.Compute/disks/delete",
    "Microsoft.Network/*/read",
    "Microsoft.Network/networkSecurityGroups/*",
    "Microsoft.Network/networkInterfaces/*",
    "Microsoft.Network/virtualNetworks/subnets/join/action",
    "Microsoft.Network/publicIPAddresses/*"
]
```

## CLI source code and tests

CLI source code and tests are in the [Acid-cli](https://github.com/Accelize/acid-cli) 
repository.

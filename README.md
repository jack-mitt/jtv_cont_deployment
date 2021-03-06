# Introduction

  This (deployment.py) is a script to automate deployments for JTV using coretools. This project
  is implemented with jenkins and must be given the deploy command(s) and servers
  to deploy to. For each server given the script disables solarwinds alerts, checks
  if it is available to be removed from its pools, then runs the deploy command on
  it, and finally puts the server back into each pool. Status updates are sent to
  the cont-deploy slack channel.

### Solarwinds

  Unless the bug has been fixed, normal domain accounts cannot run queries on the Solarwinds
  database. To get around this Jeremy or one of the other windows admins will have
  to create a special "local" account for you. To disable alerts in solarwinds you must
  pass a node ID to the API call. The query is to get the Node ID.



# Getting Started

  The current Jenkins job can be found [here](http://build.jewelry.acn/jenkins/job/gardeners/job/dev/job/gardeners-jack-DEPLOY-TO-DEV/). To
  configure where and what should be deployed you can either edit the command line input under the configure tab or edit the
  *EnvVars.txt* file.

### Requirements
  This script requires the following python libraries:
      orionsdk
      requests
      paramiko
      f5.bigip


### Command Line

  On the command line *--command* is used to specify the deploy command that will be run
  and all servers that need to be deployed to should be listed on the command line, exactly
  as they appear in the f5 (more information on command line options can be found when running
  the script with *--help*).

  ![alt text](https://github.com/jack-mitt/jtv_cont_deployment/blob/master/images/command_line.png "Command line input")

  In this example the *sudo -u core coretools --restart=current* will be run on *psbedl119* and *psbeql06*.

### Vars File

  With the vars file option one execution of the script can run multiple deploy commands.
  In *EnvVars.txt* lines either start with **command:** or **server:**. Commands are placed
  before each server that that command should be run on. For the script to know to look in the vars file,
  you must use the *--automated* option. Here is an example of the layout:

  ![alt text](https://github.com/jack-mitt/jtv_cont_deployment/blob/master/images/vars_file.png "Vars file input")

  In this example the first command will run on psbedl119 only and the second
  command will run only psbeql06.

# Missing Pieces

  This script has a few problems that will need to be fixed before it can be safely used.

### Secrets

  Currently this script needs secrets in three locations: authenticating to the
  f5 and solarwinds APIs, a sudo password for the user running the script, and the
  decryption password of the servers that the script is running on. I was unable to find
  an efficient and safe library that acts as an encrypted wallet for this script.

### Checking no important jobs are running on batch servers

  This will require editing the coretools code. There should be an API call that
  retrieves all running jobs on a batch server and check them against a list of
  predetermined jobs that we will not stop. Unless the user says that it is ok.

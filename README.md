# Introduction

 'this' is a script to automate deployments for JTV using coretools. This project
  is implemented with jenkins and must be given the deploy command(s) and servers
  to deploy to. For each server given the script disables solarwinds alerts, checks
  if it is available to be removed from its pools, then runs the deploy command on
  it, and finally puts the server back into each pool. Status updates are sent to
  the cont-deploy slack channel.

# Getting Started

  The current Jenkins job can be found [here](http://build.jewelry.acn/jenkins/job/gardeners/job/dev/job/gardeners-jack-DEPLOY-TO-DEV/). To
  configure where and what should be deployed you can either edit the command line input under the configure tab or edit the
  *EnvVars.txt* file.

### Command Line

  On the command line *--command* is used to specify the deploy command that will be run
  and all servers that need to be deployed to should be listed on the command line, exactly
  as they appear in the f5 (more information on command line options can be found when running
  the script with *--help*)

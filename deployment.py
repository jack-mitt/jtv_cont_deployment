import os
import orionsdk
import paramiko
import subprocess
import sys
import f5.bigip
import getpass
import datetime
import time
import requests


SLACK_URL = "https://apachevendorproxy.jewelry.acn:16443/slack/services/TBGR28FL0/BKSPXM88J/7BckZMomprTI9oNK8JKkL0hA"
def main():

    #set env variables to get around proxy
    proxies = {
        "http": None,
        "https": None,
    }
    os.environ['no_proxy'] = "localhost,127.0.0.1,solarwinds.jewelry.acn,*.jewelry.qa,*.jewelry.dev,*.jewelry.rx"

    '''
        # This is the main process for the script. It calls methods for each
        # step of the deployment process. Using the given enviornment variables,
        # server names, and coretools --deploy command. For each server given this
        # method will disable alerts on the server, check if there is another
        # enabled node in its pool, if there is, it will disable it then ssh to it
        # and run the deploy command, then reenable it and its alerts.
    '''
    def startup():

        send_slack_message("Starting deployment...")

        serverList = [] #list of servers to deploy to
        notDeployed = [] #list of servers where the deployment failed

        VARS = {}
        if len(sys.argv) == 1: #check if servers were given
            #send_slack_message("ERROR: no servers to deploy to provided.")
            print("ERROR: No servers to deploy to given.")
            printHelp()
            sys.exit(1)

        #read command line arguments
        coreToolsCommand = None
        downtime = 15
        VARS["username"] = None
        env_vars_file = "./EnvVars.txt" #Vars file that contains commands to deploy and servers to deploy to
        vars_file = "./DevVars.txt.decrypted" #Vars file that contains secrets
        max_connections = None #Max connections that we can shut down a server with
        polite = False #Whether or not to check for important batch jobs
        automated = False #Whether or not we are reading servers from EnvVars
        ######THIS NEEDS TO BE ADDRESSED
        for i in range(1, len(sys.argv)):
            if "--" in sys.argv[i]:
                if "username" in sys.argv[i]:
                    VARS["username"] = sys.argv[i].split("=")[1]
                elif "downtime" in sys.argv[i]:
                    downtime = int(sys.argv[i].split("=")[1])
                elif "help" in sys.argv[i]:
                    printHelp()
                    sys.exit(1)
                elif "envvars" in sys.argv[i]:
                    env_vars_file = sys.argv[i].split("=")[1]
                elif "connections" in sys.argv[i]:
                    max_connections = int(sys.argv[i].split("=")[1])
                elif "polite" in sys.argv[i]:
                    polite = True
                elif "uservars" in sys.argv[i]:
                    vars_file = sys.argv[i].split("=")[1]
                elif "automated" in sys.argv[i]:
                    automated = True
                elif "command" in sys.argv[i]:
                    command = sys.argv[i].split("=")[1:]
                    command = "=".join(command)
                    command_len = len(command.split(" "))
                    i += command_len
                    coreToolsCommand = command


            else:
                serverList.append(sys.argv[i])


        VARS = readVariables(vars_file) #get secrets

        print()
        print("Connecting to the solarwinds api", end="...")
        sys.stdout.flush()
        try:
            swis = orionsdk.SwisClient("solarwinds.jewelry.acn", VARS["username"], VARS["solarwinds-pass"]) #connect to solarwinds api
        except Exception as e:
            if "401" in str(e):
                send_slack_message("ERROR: Invalid solarwinds credentials.")
                print("ERROR: Invalid Credentials")
                sys.exit(1)
            else:
                send_slack_message("ERROR: Could not connect to the solarwinds API.")
                print("Error connecting to the solarwinds API.")
                sys.exit(1)
        print("Done")

        print("Connecting to the F5 management interface", end="...")
        sys.stdout.flush()
        try:
            mgmt = f5.bigip.ManagementRoot("qaltm01.net.jewelry.acn", VARS["username"], VARS["password"]) #connect to f5 api
        except Exception as e:
            if "401" in str(e):
                send_slack_message("ERROR: Invalid f5 credentials.")
                print("ERROR: Invalid Credentials")
                sys.exit(1)
            else:
                send_slack_message("ERROR: Could not connect to the f5 management interface.")
                print("Error: Could not connect to the f5 management interface.")
                sys.exit(1)
        print("Done")

        notDeployed = []
        if automated:
            deployments = read_servers(env_vars_file)
            for command in deployments:
                nohup_index = command.find("core") + 5
                first_half = command[:nohup_index]
                second_half = command[nohup_index:]
                first_half = first_half + "/bin/nohup " #add nohup so that the process does not end on logout. (man nohup)
                nohup_command = first_half + second_half
                notDeployed += deploy_to_servers(nohup_command, deployments[command], swis, mgmt, VARS, downtime, max_connections)
        else:
            if coreToolsCommand == None:
                coreToolsCommand = input("Input the given coretools command: ") #deploy command
            if polite == True:
                coreToolsCommand += "--polite"
            check_command(coreToolsCommand)
            nohup_index = coreToolsCommand.find("core") + 5
            first_half = coreToolsCommand[:nohup_index]
            second_half = coreToolsCommand[nohup_index:]
            first_half = first_half + "/bin/nohup " #add nohup so that the process does not end on logout. (man nohup)
            nohup_command = first_half + second_half
            notDeployed += deploy_to_servers(nohup_command, serverList, swis, mgmt, VARS, downtime, max_connections)

        if len(notDeployed) > 0:
            listFailedDeploys(notDeployed)

    #attempt to deploy to each server
    def deploy_to_servers(coreToolsCommand, serverList, swis, mgmt, VARS, downtime, max_connections):
        notDeployed = []
        for server in serverList:
            nodeID = None
            if ":" in server:
                serverName = server.split(":")[0]
            else:
                serverName = server
            if "." not in serverName:
                serverName = serverName.lower()
                serverName += ".jewelry.acn"

            print()
            print("DEPLOYING TO " + serverName)
            send_slack_message("Deploying to " + serverName)
            print("Fetching node ID", end="...")
            sys.stdout.flush()
            nodeID = getNodeID(VARS, swis, serverName)
            if nodeID == None:
                print("ERROR: No node with name " + serverName + " found - moving to next node.")
                send_slack_message("ERROR: Could not find node ID that corresponds to " + serverName + " in solarwinds.")
                notDeployed.append(serverName)
                continue
            print("Done")
            print("Node ID = " + str(nodeID))

            print("Disabling alerts", end="...")
            status = disableAlerts(VARS, swis, nodeID, downtime)
            if status == False:
                print("Failed to disable alerts - moving to next node.")
                send_slack_message("ERROR: Could not disable alerts on " + serverName)
                notDeployed.append(serverName)
                continue
            else:
                print("Done")

            print("Checking node's availability", end="...")
            sys.stdout.flush()
            available, resourceObjects, currentPools = checkAvailability(VARS, mgmt, server, max_connections)
            print("Done")

            #check if there is at least 1 other server up in the same node
            #turn server offline

            if available == True:
                for i in range(0, len(resourceObjects)):
                    print("Pulling " + resourceObjects[i].name + " out of " + currentPools[i].name, end="...")
                    sys.stdout.flush()
                    status = forceOffline(resourceObjects[i])
                    if status == False:
                        print("FAIL")
                        send_slack_message("ERROR: Could not force " + serverName + " offline.")
                        print("Enabling alerts and moving to next node", end="...")
                        sys.stdout.flush()
                        notDeployed.append(serverName)
                        if enableAlerts(VARS, swis, nodeID) == False:
                            print("Failed to enable alerts. It will have to be done manually.")
                        else:
                            print("Done")
                        continue
                    else:
                        print("Done")

                deploy_status = deployToServer(VARS, serverName, coreToolsCommand)
                if deploy_status == False:
                    print("FAIL")


                for i in range(0, len(resourceObjects)):
                    print("Putting " + resourceObjects[i].name + " back into " + currentPools[i].name, end="...")
                    sys.stdout.flush()
                    status = forceOnline(resourceObjects[i])
                    if status == False:
                        print("FAIL: " + serverName + " will have to enabled manually.")
                        send_slack_message("Deployment successful on " +  serverName + ", but could not add server back to " + currentPools[i].name)
                        print("Enabling alerts and moving to next node", end="...")
                        sys.stdout.flush()
                        if enableAlerts(VARS, swis, nodeID) == False:
                            print("Failed to enable alerts. It will have to be done manually.")
                        else:
                            print("Done")
                            print()
                        continue
                    else:
                        print("Done")

                if deploy_status == False:
                    send_slack_message("Deployment to " + serverName + " failed.")
                else:
                    send_slack_message("Deployment to " + serverName + " complete")

            else:
                print("Error: Could not deploy to " + serverName + ". There must be at least one other node up in all relevant pools.")
                send_slack_message("ERROR: Could not pull " + serverName + " out of its pools. There must be at least one other node up in all relevant pools.")
                notDeployed.append(serverName)

            print("Enabling alerts", end="...")
            sys.stdout.flush()
            status = enableAlerts(VARS, swis, nodeID)
            if status == False:
                print("FAIL")
            else:
                print("DONE")

        return notDeployed





    '''
     # This method checks a certain node to make sure that it is not the last
     # online node in one of the pools that it is in. If there are no other Nodes
     # online in at least one of the pools that the current node is in then this
     # method will return false, else true.
    '''
    def checkAvailability(VARS, mgmt, server, max_connections):
        pools = mgmt.tm.ltm.pools.get_collection()
        currentPools = [] #the pools that contain the node we want to disable
        resourceObjects = []
        tempPool = None
        available = True
        thisPool = None
        targetMember = None
        server = server.lower()
        for pool in pools:
            members = pool.members_s.get_collection()
            for member in members:
                if server in member.name.lower():
                    resourceObjects.append(member)
                    targetMember = member
                    currentPools.append(pool)
                    if targetMember.state == "user-down" or targetMember.session == "user-disabled": #check if node is disabled
                        return False, resourceObjects, currentPools

        #check if node with that name was not found
        if targetMember == None:
            return False, resourceObjects, currentPools

        for pool in currentPools:
            members = pool.members_s.get_collection()
            thisPool = False
            for member in members:

                if member.name.lower() == server.lower():
                    stats_path = "https://localhost/mgmt/tm/ltm/pool/~Common~" + pool.name + "/members/~Common~" + member.name + "/stats"
                    cur_conns = int(member.stats.load().raw["entries"][stats_path]["nestedStats"]["entries"]["serverside.curConns"]["value"]) #get the current server-side connections
                    if max_connections != None and cur_conns > max_connections:
                        print("Error too many connections on the server: " + str(cur_conns))
                        send_slack_message("ERROR: " + serverName + " has too many active connections.")
                        return False, resourceObjects, currentPools
                    else:
                        print("Current connections: " + str(cur_conns), end="...")

                if len(members) > 1:
                    if server not in member.name.lower():
                        if "up" in member.state:
                            thisPool = True
                else:
                    thisPool = True
            if thisPool == False:
                available = False
                return available, resourceObjects, currentPools
        return available, resourceObjects, currentPools

    '''
     # This method runs a query on the solarwinds database to fetch the ID of the
     # current node using its DNS name.
    '''
    def getNodeID(VARS, swis, serverName):
        try:
            nodeID = swis.query("SELECT NodeID from Orion.Nodes WHERE DNS='" + serverName + "'" )
            return nodeID["results"][0]["NodeID"]
        except:
            return None

    '''
     # This method SSH's to the node then runs the coretools command on it.
     # If nothing is given from stderr it will return true, else false.
    '''
    def deployToServer(VARS, serverName, coreToolsCommand):
        connection = paramiko.SSHClient()
        connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        is_running_command = "sudo -u core /services/support/autodeploy/coretools_testing/coretools --isrunning=current"
        '''
        ### we will need this code once corey gets the ssh agent creds working on jenkins ###

        ssh_agent = paramiko.agent.Agent()
        ssh_keys = ssh_agent.get_keys()
        if len(ssh_keys) == 0:
            send_slack_message("ERROR: Could not find ssh agent keys, please add them.")
            print("Could not find ssh agent keys, please add them.")
            return False


        print("SSHing to node", end="...")
        sys.stdout.flush()
        try:
            for key in ssh_keys:
                connection.connect(serverName, username=VARS["username"], pkey=key)
            print("Done")
            sys.stdout.flush()
        except:
            print("Failed to ssh to node.")
            return False
        '''

        print("SSHing to node", end="...")
        sys.stdout.flush()
        try:
            connection.connect(serverName, username=VARS["username"], password=VARS["password"])
            print("Done")
            sys.stdout.flush()
        except:
            send_slack_message("Failed to ssh to " + serverName)
            print("Failed to ssh to node.")
            return False

        print("Running the deployment script", end="...")
        print(coreToolsCommand)
        sys.stdout.flush()

        connection_stdin, connection_stdout, connection_stderr = connection.exec_command(coreToolsCommand, get_pty=True)
        try:
            time.sleep(3)
            connection_stdin.write(VARS["password"] + "\n")
            time.sleep(3)
            connection_stdin.write(VARS["devpass"] + "\n")
        except:
            print("Error writing over socket.")
            send_slack_message("Error writing password over socket.")
            return False

        output = connection_stdout.read() #deploy out
        err = connection_stderr.read() #deploy std_err
        print(err)
        if len(err) > 3:
            err = format_coretools_out(err, VARS)
            return False

        output = format_coretools_out(output, VARS) #output from coretools --deploy without secrets
        connection_stdin, connection_stdout, connection_stderr = connection.exec_command(is_running_command, get_pty=True)
        try:
            connection_stdin.write(VARS["password"] + "\n")
        except:
            print("Error writing over socket.")
            send_slack_message("Error writing password over socket.")
            return False
        output = connection_stdout.read()
        err = connection_stderr.read()
        if len(err) > 0:
            print(err)
            return False
        check_output = format_coretools_out(output, VARS) #output from coretools --isrunning without secrets
        if "CORRECT" in check_output:
            print("SUCCESS")
            return True
        else:
            print("Deploy command run, however the incorrect process is running.")
            return False
    '''
     # This method disables alerts on a node using the solarwinds API.
    '''
    def disableAlerts(VARS, swis, NodeID, downtime):
        server = "swis://local/Orion/Orion.Nodes/NodeID=" + str(NodeID)
        try:
            swis.invoke('Orion.AlertSuppression', 'SuppressAlerts',
                [ server ],
                datetime.datetime.now(),
                datetime.datetime.now() + datetime.timedelta(downtime)
                )
            return True
        except:
            return False

    '''
     # This method enables alerts on a node using the solarwinds API.
    '''
    def enableAlerts(VARS, swis, NodeID):
        server = "swis://local/Orion/Orion.Nodes/NodeID=" + str(NodeID)
        try:
            swis.invoke("Orion.AlertSuppression", "ResumeAlerts", [ server ])
            return True
        except:
            return False

    '''
     # This method lists the servers that the deployment failed on.
    '''
    def listFailedDeploys(notDeployed):
        print()
        print("The following servers were not deployed to: ")
        for server in notDeployed:
            print(server)

    '''
    # This method forces a node offline
    '''
    def forceOffline(member):
        member.state = "user-down"
        member.session = "user-disabled"
        try:
            member.update()
            return True
        except:
            return False

    '''
    # This method turns a node online
    '''
    def forceOnline(member):
        member.state = "user-up"
        member.session = "user-enabled"
        try:
            member.update()
            return True
        except:
            return False

    def printHelp():
        print("Usage: deployment.py [options] [servers] [to] [deploy] [to]")
        print("     Script to automate JTV deployments to f5 nodes.")
        print()
        print("Options:")
        print("     --help                   Show this help message and exit")
        print()
        print("     --username=USERNAME      The jtv username that will be used to ssh")
        print("                              to each server and connect to the API.")
        print()
        print("     --downtime=DOWNTIME      Integer value, the number of minutes")
        print("                              that alerts will be disabled for")
        print("                              (alerts are still automatically reenabled).")
        print()
        print("     --vars=/path/to/file     The path to the file that will contain the  ")
        print("                              environment variables. Formatting: --key:value")
        print()
        print("     --connections=MAX_CONNECTIONS")
        print("                               The maximum amount of connections that a server")
        print("                               can have before it is available to be taken offline.")

    '''
    #Read the variables given in DevVars.txt
    '''
    def readVariables(path):
        VARS = {}
        lines =  open(path, "r").readlines()
        for line in lines:
            if "--" in line:
                line = line[2:]
                line = line.strip(" \n")
                line = line.split(":")
                VARS[line[0]] = line[1]
        return VARS
    '''
    #Send Status updates to slack. Current channel: cont-deploy
    '''
    def send_slack_message(message):
        data = {"text": message}
        r = requests.post(url=SLACK_URL, json=data, verify='/etc/pki/ca-trust/extracted/openssl/ca-bundle.trust.crt')

    '''
    #Read the commands and servers given in EnvVars.txt
    '''
    def read_servers(path):
        deployments = {}
        lines = open(path, "r").readlines()
        cur_command = None
        for line in lines:
            if "command" in line:
                line = line.strip(" \n")
                line = line.split(":")
                cur_command = line[1]
                deployments[cur_command] = []
            elif "server" in line:
                line = line.strip(" \n")
                line = line.split(":")
                server = line[1]
                if cur_command != None:
                    deployments[cur_command].append(server)
                else:
                    print("Error incorrect formatting of command / server file. Please use --help")
        return deployments
    '''
    #make sure we were given a valid unix command
    '''
    def check_command(coreToolsCommand):
        if coreToolsCommand[0] == " ":
            print("Invalid Command.")
            send_slack_message("Error: Invalid deploy command.")
            sys.exit(1)
        unixCommand = coreToolsCommand.split(" ")[0]
        cmd = ["command", unixCommand]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode == 127:
            print("Invalid Command.")
            send_slack_message("ERROR: Invalid deploy command.")
            sys.exit(1)

        #check if no deploy command was given
        if len(coreToolsCommand) == 0:
            print("ERROR: No coretools command was given.")
            sys.exit(1)

    '''
    #remove secrets from coretools output
    '''
    def format_coretools_out(output, VARS):
        output = output.decode()
        index = output.find("[sudo]")
        format_out = output[index:]
        for k in VARS:
            if VARS[k] in format_out:
                first_index = format_out.find(VARS[k])
                x = format_out[:first_index]
                y = format_out[first_index + len(VARS[k]):]
                format_out = x + y
        return format_out

    startup()

main()

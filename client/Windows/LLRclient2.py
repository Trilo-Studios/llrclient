from PodSixNet.Connection import connection
from PodSixNet.Connection import ConnectionListener
import PodSixNet

import time
import sys
import os
import shutil
import subprocess
import signal
import atexit
import socket

o= open(os.getcwd()+ '/settings.txt', 'r').readlines()

for line in o:
    line= line.replace(' ', '')
    if line.startswith('clientname'):
        name= line.split('=')[1].replace('\n', '')
    if line.startswith('numthreads'):
        numthreads= int(line.split('=')[1])
    if line.startswith('extrawork'):
        extrawork= int(line.split('=')[1])
    if line.startswith('port'):
        port= int(line.split('=')[1])
    if line.startswith('ip'):
        ip= line.split('=')[1].replace('\n', '')
    if line.startswith('verbose'):
        verbose= int(line.split('=')[1].replace('\n', ''))
        
class NetworkListenor(ConnectionListener):
    def __init__(self, host, port):
        self.Connect(address=(host, port))
        self.connected= False
        self.candidates= []
        self.serveractive= True
        self.wait= False
        self.recievedping= False
        
        if verbose:
            print('client started')
        
    def Network(self, data):
        pass

    def Network_connected(self, data):
        if verbose:
            print("connected to the server")
            
        self.connected= True
        self.recievedping= True
        global numthreads
        connection.Send({'action':'nickname', 'nick': name, 'cores': numthreads})
	
    def Network_error(self, data):
        print("error: ", data['error'])
        connection.Send({'action': 'clienterror', 'data':data['error']})
	
    def Network_disconnected(self, data):
        if verbose:
            print("disconnected from the server")
        self.connected= False
	
    def Network_welcome(self, data):
        self.wait= True
        self.recievedping= True
        if verbose:
            print('recieved from server:' ,data['msg'])

    def getload(self, amount):
        if amount > 0:
            connection.Send({'action':'getload', 'amount': amount})

    def Network_newcandidates(self, data):
        global prevresults
        if verbose:
            print('recieved new candidates')
        p= []
        if verbose:
            print('current:', self.candidates)
            print('newcand:', data['data'])
        for n in prevresults:
            p.append(n.split(' ')[0])
        if verbose:
            print('tested:', p)
        for c in data['data']:
            if c in self.candidates+p:
                if verbose:
                    print('got already reserved/done candidate from server:', c)
            else:
                self.candidates.append(c)
        if verbose:
            print('after:', self.candidates)
        if len(data['data'])== 0:
            self.serveractive= False
        else:
            self.serveractive= True

    def sendTest(self, t):
        connection.Send({'action': 'completetest', 'data':t})

    def close(self):
        connection.close()

    def Network_ping(self, data):
        self.recievedping= True
        if verbose:
            print('recieved ping')
        connection.Send({'action': 'pingsuccess'})

    def sendping(self):
        connection.Send({'action': 'ping'})

    def Network_pingsuccess(self, data):
        self.recievedping= True
        
def cleanup(a, b):
    global threads, client
    if verbose:
        print('killing threads')
    for thread in threads:
        thread.kill()
        thread.wait()
    if verbose:
        print('exiting')
    client.close()
    del client
    sys.exit()

threads= []
prevresults= []
for sig in (signal.SIGABRT, signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, cleanup)
atexit.register(cleanup, threads)

client= NetworkListenor(ip, port)
while not client.connected: #wait until the connection is formed until we continue
    connection.Pump()
    client.Pump()
    time.sleep(0.01)
    
for _ in range(50): #wait to see if server sends us candidates so we don't ask for duplicates
    connection.Pump()
    client.Pump()
    time.sleep(.1)
    
if len(client.candidates) < extrawork*numthreads: #only ask for work if we are below our threshold
    client.getload(extrawork*numthreads-len(client.candidates))

if not os.path.isdir(os.getcwd()+'\\llr'):
    os.makedirs(os.getcwd()+ '\\llr')

if 'win' in sys.platform:
    loc= '\\cllr64.exe'
    letter= 'c'
elif 'linux' in sys.platform:
    loc= '/sllr64'
    letter= 's'
else:
    raise Exception('only linux and windows supported')


while len(client.candidates)==0: #wait for candidates to be recieved
    if not client.serveractive:
        client.getload(extrawork*numthreads)
    time.sleep(0.1)
    connection.Pump()
    client.Pump()
    

for c in range(1, numthreads+1):
    if not os.path.isdir(os.getcwd()+ '/llr/llr'+ str(c)):
        os.makedirs(os.getcwd()+ '/llr/llr'+ str(c))
        shutil.copy2(os.getcwd()+ loc, os.getcwd()+ '\\llr\\llr'+str(c))

    if verbose:
        print('starting llr test on', client.candidates[0])
    threads.append(subprocess.Popen(os.getcwd()+ '/llr/llr'+ str(c)+'/' +letter+'llr64 -d -q"'+client.candidates[0]+'"',
                   stdout= subprocess.PIPE, stderr= subprocess.PIPE, cwd= os.getcwd()+ '/llr/llr'+ str(c),
                                    creationflags= 0x00000008, universal_newlines=True))
    del client.candidates[0]

latestping= time.time()
client.sendping()
while True:
    connection.Pump()
    client.Pump()
    
    if not client.serveractive: #if server is out of candidates keep asking
        client.getload(extrawork*numthreads-len(client.candidates))
    if not client.connected or (len(client.candidates)== 0 and client.serveractive):
        if verbose:
            print('not connected, trying to connect...')
        prev= client.candidates
        client= NetworkListenor(ip, port)
        client.candidates= prev
        connection.Pump()
        client.Pump()
        time.sleep(1) #wait for server communication
        connection.Pump()
        client.Pump()
        for i in prevresults:
            client.sendTest(i)
        client.getload(int(extrawork*numthreads)- len(client.candidates))
        time.sleep(1) #wait for candidates to come in
        connection.Pump()
        client.Pump()
        if client.wait: 
            while len(client.candidates)== 0: #we have some connection with the server
                client.Pump()                 #waiting for candidates to come
                connection.Pump()


    i= 0
    for thread in threads[:]:
        connection.Pump()
        client.Pump()
        try:
            z= thread.communicate(timeout= 1)[0]
        except subprocess.TimeoutExpired: #llr test is still in progress
            pass
        else: #llr test has finished
            #print('here')
            #print('error:', thread.stderr.readlines())
            try:
                #z= thread.stdout.readlines()[-1]
                z= z.split('\n')[-2]
                print('out:', z)
                #z= thread.stdout.readlines()[-1].decode('utf-8').split('\r')[-2]
                #z= z[-1].decode('utf-8').split('\r')[-2]
            except IndexError:
                #this happens when server is out of candidates and we are trying to read data twice
                print('indexError')
            else:
                prevresults.append(z)
                if len(prevresults) > (numthreads*extrawork+10):
                    del prevresults[0]
                if verbose:
                    print('finished test on', z)
                client.sendTest(z)
            if len(client.candidates)!= 0:
                if verbose:
                    print('starting llr test on', client.candidates[0])
                threads[i]= subprocess.Popen(os.getcwd()+ '/llr/llr'+ str(i+1)+'/' +letter+'llr64 -d -q"'+client.candidates[0]+'"',
                       stdout= subprocess.PIPE, stderr= subprocess.PIPE, cwd= os.getcwd()+ '/llr/llr'+ str(i+1), creationflags= 0x00000008, universal_newlines=True)
                del client.candidates[0]
                if len(client.candidates) < numthreads*extrawork:
                    # if we are keeping too many candidates wait to ask for more
                    client.getload(1)
        if time.time() - latestping > 60:
            latestping= time.time()
            if not client.recievedping:
                client.connected= False
                backup= client.candidates
            else:
                client.sendping()
            client.recievedping= False
            
            

        i+= 1
        time.sleep(0.1)
        
